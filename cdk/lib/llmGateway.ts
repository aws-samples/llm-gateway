/**
 * Copyright 2023 Amazon.com, Inc. and its affiliates. All Rights Reserved.
 *
 * Licensed under the Amazon Software License (the "License").
 * You may not use this file except in compliance with the License.
 * A copy of the License is located at
 *
 *   http://aws.amazon.com/asl/
 *
 * or in the "license" file accompanying this file. This file is distributed
 * on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
 * express or implied. See the License for the specific language governing
 * permissions and limitations under the License.
 */

import * as apigw from "aws-cdk-lib/aws-apigateway";
import * as apigwv2 from "@aws-cdk/aws-apigatewayv2-alpha";
import { WebSocketLambdaIntegration } from "@aws-cdk/aws-apigatewayv2-integrations-alpha";
import * as cdk from "aws-cdk-lib";
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as iam from "aws-cdk-lib/aws-iam";
import * as wafv2 from "aws-cdk-lib/aws-wafv2";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as logs from "aws-cdk-lib/aws-logs";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as path from "path";
import { Construct } from "constructs";
import * as fs from "fs";
// Local
import { HttpMethod } from "aws-cdk-lib/aws-events";

/* At present, Amazon Bedrock streaming is supported by:
 * - Anthropic Claude
 * - AI21 Labs Jurassic-2
 * - Cohere Command
 * - Stability.ai Diffusion
 */
const bedrockModels = {
  // AI21
  "ai21.j2-mid-v1": {},
  "ai21.j2-ultra-v1": {},
  // Amazon
  "amazon.titan-embed-text-v1": {},
  // "amazon.titan-text-express-v1": "",  // Not yet available.
  // Anthropic
  "anthropic.claude-v2": {},
  "anthropic.claude-v1": {},
  "anthropic.claude-instant-v1": {},
  // Cohere
  "cohere.command-text-v14": {},
};

const chatHistoryTableName = "ChatHistory";

export class LlmGatewayStack extends cdk.Stack {
  stackPrefix = "LlmGateway";
  embeddingsModel = "amazon.titan-embed-text-v1";

  // Environment variables
  defaultMaxTokens = String(process.env.DEFAULT_MAX_TOKENS || 4096);
  defaultTemp = String(process.env.DEFAULT_TEMP || 0.0);
  hasIamAuth = String(process.env.API_GATEWAY_USE_IAM_AUTH).toLowerCase() == "true";
  regionValue = String(process.env.REGION_ID || "us-east-1");
  restEcrRepoName = process.env.ECR_REST_REPOSITORY;
  useApiKey = String(process.env.API_GATEWAY_USE_API_KEY).toLowerCase() == "true";
  wsEcrRepoName = process.env.ECR_WEBSOCKET_REPOSITORY;
  opensearchDomainEndpoint = process.env.OPENSEARCH_DOMAIN_ENDPOINT || "";
  vpc = process.env.VPC || null;
  vpcSubnets = process.env.VPC_SUBNETS || null;
  vpcSecurityGroup = process.env.VPC_SECURITY_GROUP || null;

  tryGetParameter(parameterName: string, defaultValue: any = null) {
    const parameter = this.node.tryFindChild(parameterName) as cdk.CfnParameter;
    if (parameter) {
      return parameter.valueAsString;
    } else {
      console.error(`Parameter ${parameterName} not found.`);
      return defaultValue;
    }
  }

  createSecureDdbTable(tableName: string, partitionKeyName: string) {
    const table = new dynamodb.Table(this, tableName, {
      partitionKey: {
        name: partitionKeyName,
        type: dynamodb.AttributeType.STRING,
      },
      encryption: dynamodb.TableEncryption.AWS_MANAGED,
      pointInTimeRecovery: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    return table;
  }

  createLlmGatewayLambdaRole(
    roleName: string,
    apiId: string,
    chatHistoryTable: dynamodb.Table
  ) {
    const resourceArn = null;
    return new iam.Role(this, roleName, {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      roleName: roleName,
      inlinePolicies: {
        LambdaPermissions: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              sid: "InvokeBedrock",
              effect: iam.Effect.ALLOW,
              actions: [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
              ],
              resources: ["*"],
            }),
            new iam.PolicyStatement({
              sid: "WebsocketExecution",
              effect: iam.Effect.ALLOW,
              actions: ["execute-api:ManageConnections", "execute-api:Invoke"],
              resources: [
                `arn:aws:execute-api:${this.region}:${this.account}:${apiId}/*`,
              ],
            }),
            new iam.PolicyStatement({
              sid: "HistoryDynamoDBAccess",
              effect: iam.Effect.ALLOW,
              actions: [
                "dynamodb:BatchWriteItem",
                "dynamodb:DeleteItem",
                "dynamodb:GetItem",
                "dynamodb:PutItem",
                "dynamodb:Query",
                "dynamodb:Scan",
                "dynamodb:UpdateItem",
              ],
              resources: [chatHistoryTable.tableArn],
            }),
            new iam.PolicyStatement({
              sid: "WriteToCloudWatchLogs",
              effect: iam.Effect.ALLOW,
              actions: [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents",
              ],
              resources: ["*"],
            }),
          ],
        }),
      },
    });
  }

  configureVpcParams(): object {
    if (Boolean(this.vpc) && Boolean(this.vpcSubnets) && Boolean(this.vpcSecurityGroup)) {
      return {
        vpc: this.vpc,
        vpcSubnets: { subnets: this.vpcSubnets },
        securityGroups: [this.vpcSecurityGroup],
      }
    }
    return {}
  }

  createRestApi(bedrockEcr: ecr.IRepository, chatHistoryTable: dynamodb.Table) {
    // Create a CloudWatch Logs Log Group
    const restApiLogGroup = new logs.LogGroup(this, "RestApiLogGroup", {
      retention: logs.RetentionDays.ONE_MONTH, // Adjust as needed.
    });

    const api = new apigw.RestApi(this, "LlmGatewayRest", {
      defaultCorsPreflightOptions: {
        allowOrigins: apigw.Cors.ALL_ORIGINS,
        allowCredentials: true,
      },
      deployOptions: {
        accessLogDestination: new apigw.LogGroupLogDestination(restApiLogGroup),
        accessLogFormat: apigw.AccessLogFormat.jsonWithStandardFields(),
      },
    });

    api.addRequestValidator("RequestValidator", {
      requestValidatorName: "RequestValidator",
      validateRequestBody: true,
      validateRequestParameters: true,
    });

    const greetModel = new apigw.Model(this, "request", {
      restApi: api,
      contentType: "application/json",
      description: "Validate LLM request body",
      modelName: "llmgatewaymodel",
      schema: {
        type: apigw.JsonSchemaType.OBJECT,
        required: ["prompt", "parameters"],
        properties: {
          prompt: { type: apigw.JsonSchemaType.STRING },
          parameters: {
            type: apigw.JsonSchemaType.OBJECT,
            properties: {
              temperature: { type: apigw.JsonSchemaType.NUMBER },
              stop_sequences: { type: apigw.JsonSchemaType.STRING },
              max_tokens_to_sample: { type: apigw.JsonSchemaType.NUMBER },
            },
          },
        },
      },
    });

    if (this.useApiKey) {
      // Create an API Key
      const apiKey = new apigw.ApiKey(this, "ApiKey", {
        apiKeyName: "api-key",
      });
      // Add usage plan and associate the API Key
      const usagePlan = new apigw.UsagePlan(this, "UsagePlan", {
        name: "usage-plan",
      });
      usagePlan.addApiStage({
        stage: api.deploymentStage,
      });
      new cdk.CfnOutput(this, "output" + this.stackPrefix + "ApiKey", {
        value: apiKey.keyId,
      });
      new cdk.CfnOutput(this, "output" + this.stackPrefix + "Api", {
        value: api.url,
      });
    }

    // Create a Cognito user pool; authorizer; and use that for APIGW auth.
    const userPoolName = this.stackPrefix + "UserPool";
    const userPool = new cognito.UserPool(this, userPoolName, {
      userPoolName: userPoolName,
      advancedSecurityMode: cognito.AdvancedSecurityMode.ENFORCED,
      passwordPolicy: {
        minLength: 8,
        requireUppercase: true,
        requireLowercase: false, // Optional based on your requirements
        requireDigits: true,
        requireSymbols: true,
      },
    });

    const authorizerName = "Authorizer";
    const apiAuthorizer = new apigw.CfnAuthorizer(this, authorizerName, {
      name: authorizerName,
      identitySource: "method.request.header.Authorization",
      providerArns: [userPool.userPoolArn],
      restApiId: api.restApiId,
      type: apigw.AuthorizationType.COGNITO,
    });


    for (const modelKey of Object.keys(bedrockModels)) {
      // It's more secure for each lambda to have its own role, despite the clutter.
      const lambdaRole = this.createLlmGatewayLambdaRole(
        this.stackName + "RestLambda" + modelKey,
        api.restApiId,
        chatHistoryTable
      );


      // Create Lambda function from the ECR image.
      const vpcParams = this.configureVpcParams();
      const fn = new lambda.DockerImageFunction(this, modelKey, {
        code: lambda.DockerImageCode.fromEcr(bedrockEcr, { tag: "latest" }),
        role: lambdaRole,
        environment: {
          CHAT_HISTORY_TABLE_NAME: chatHistoryTableName,
          DEFAULT_TEMP: this.defaultTemp,
          DEFAULT_MAX_TOKENS: this.defaultMaxTokens,
          REGION: this.regionValue,
          MODEL: modelKey,
          EMBEDDINGS_MODEL: this.embeddingsModel,
          OPENSEARCH_DOMAIN_ENDPOINT: this.opensearchDomainEndpoint,
          OPENSEARCH_INDEX: "llm-rag-hackathon",
        },
        timeout: cdk.Duration.minutes(15),
        memorySize: 512,
        ...vpcParams,
      });

      // Define the integration between API Gateway and Lambda
      const integration = new apigw.LambdaIntegration(fn, {
        proxy: true,
      });

      // Create a resource and associate the Lambda integration
      const resource = api.root.addResource(modelKey);
      const authTypes = apigw.AuthorizationType;
      const authType = this.hasIamAuth ? authTypes.IAM : authTypes.NONE;
      resource.addMethod("POST", integration, {
        authorizationType: apigw.AuthorizationType.IAM,
        apiKeyRequired: false,
        requestValidator: new apigw.RequestValidator(
          this,
          modelKey + "BodyValidator",
          {
            restApi: api,
            requestValidatorName: modelKey + "BodyValidator",
            validateRequestBody: true,
          }
        ),
        requestModels: {
          "application/json": greetModel,
        },
      });

      const lambdaUrl = fn.addFunctionUrl({
        authType: lambda.FunctionUrlAuthType.AWS_IAM,
        cors: {
          allowedOrigins: ["*"],
          allowedHeaders: [
            "Content-Type",
            "X-Amz-Date",
            "Authorization",
            "X-Api-Key",
            "X-Amz-Security-Token",
            "X-Amz-User-Agent",
          ],
          allowedMethods: [HttpMethod.POST],
          allowCredentials: true,
        },
      });
    }
  }

  createWebsocketApi(
    bedrockEcr: ecr.IRepository,
    chatHistoryTable: dynamodb.Table
  ) {
    const api = new apigwv2.WebSocketApi(this, "LlmGatewayWebsocket");

    if (this.useApiKey) {
      // Create an API Key
      const apiKey = new apigw.ApiKey(this, "ApiKey", {
        apiKeyName: "api-key",
      });
      // Add usage plan and associate the API Key
      const usagePlan = new apigw.UsagePlan(this, "UsagePlan", {
        name: "usage-plan",
      });
      // usagePlan.addApiStage(stage);
      new cdk.CfnOutput(this, "output" + this.stackPrefix + "ApiKey", {
        value: apiKey.keyId,
      });
    }
    const stage = new apigwv2.WebSocketStage(this, "prod", {
      webSocketApi: api,
      stageName: "prod",
      autoDeploy: true,
    });

    // TODO: Add optional Cognito authentication. This could be done as follows:
    // Create a Cognito user pool; authorizer; and use that for APIGW auth.

    // Create a connections table.
    const websocketConnectionsTableName = "WebsocketConnections";
    const websocketConnectionsTable = this.createSecureDdbTable(
      websocketConnectionsTableName,
      "connection_id"
    );

    const lambdaRole = this.createLlmGatewayLambdaRole(
      this.stackName + "WebsocketLambda",
      api.apiId,
      chatHistoryTable
    );

    // Create Lambda function from the ECR image
    const vpcParams = this.configureVpcParams();
    const fn = new lambda.DockerImageFunction(
      this,
      "LlmGatewayWebsocketHandler",
      {
        code: lambda.DockerImageCode.fromEcr(bedrockEcr, { tag: "latest" }),
        role: lambdaRole,
        environment: {
          CHAT_HISTORY_TABLE_NAME: chatHistoryTableName,
          WEBSOCKET_CONNECTIONS_TABLE_NAME: websocketConnectionsTable.tableName,
          DEFAULT_TEMP: this.defaultTemp,
          DEFAULT_MAX_TOKENS: this.defaultMaxTokens,
          REGION: this.regionValue,
          MODEL: "anthropic.claude-v2", // TODO: Allow this to be anything.
          EMBEDDINGS_MODEL: this.embeddingsModel,
          OPENSEARCH_DOMAIN_ENDPOINT: this.opensearchDomainEndpoint,
          OPENSEARCH_INDEX: "llm-rag-hackathon",
        },
        timeout: cdk.Duration.minutes(15),
        memorySize: 512,
        ...vpcParams,
      }
    );

    // Add read & write permissions to the websockets connection table,
    //  so that this lambda can save and monitor its connections.
    const WebsocketDynamoDBAccessPolicy = new iam.PolicyStatement({
      sid: "WebsocketDynamoDBAccess",
      effect: iam.Effect.ALLOW,
      actions: [
        "dynamodb:DeleteItem",
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:Scan",
        "dynamodb:UpdateItem",
      ],
      resources: [websocketConnectionsTable.tableArn],
    });
    fn.addToRolePolicy(WebsocketDynamoDBAccessPolicy);

    // Create endpoints
    api.addRoute("$connect", {
      integration: new WebSocketLambdaIntegration("ConnectIntegration", fn),
      // TODO: this function should have IAM authorization on it. This can be done in the console.
    });
    api.addRoute("$disconnect", {
      integration: new WebSocketLambdaIntegration("DisconnectIntegration", fn),
    });
    api.addRoute("sendmessage", {
      integration: new WebSocketLambdaIntegration("SendMessageIntegration", fn),
    });

    return api;
  }

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Create API Gateway resources.

    const modelPolicyStore = this.createSecureDdbTable(
      this.stackPrefix + "ModelPolicyStore",
      "id"
    );
    const modelEngineName = this.stackPrefix + "ModelEngine";
    const modelEngine = this.createSecureDdbTable(modelEngineName, "id");

    // Create a chat history database.
    const chatHistoryTable = this.createSecureDdbTable(
      chatHistoryTableName,
      "id"
    );

    if (process.env.API_GATEWAY_TYPE == "rest") {
      // Assuming you have an existing ECR repository
      const ecrRepo = ecr.Repository.fromRepositoryName(
        this,
        this.restEcrRepoName!,
        this.restEcrRepoName!,
      );
      const api = this.createRestApi(ecrRepo, chatHistoryTable);

    } else if (process.env.API_GATEWAY_TYPE == "websocket") {
      // Assuming you have an existing ECR repository
      const ecrRepo = ecr.Repository.fromRepositoryName(
        this,
        this.wsEcrRepoName!,
        this.wsEcrRepoName!,
      );
      const api = this.createWebsocketApi(ecrRepo, chatHistoryTable);

    } else {
      throw Error(`Environment variable "API_GATEWAY_TYPE" must be set to either "rest" or "websocket"`)
    }
  }
}
