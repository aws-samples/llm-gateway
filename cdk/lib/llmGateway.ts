import * as apigw from "aws-cdk-lib/aws-apigateway";
import * as cdk from "aws-cdk-lib";
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as fs from "fs";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import * as path from "path";
import * as wafv2 from "aws-cdk-lib/aws-wafv2";
import { Construct } from "constructs";
import { HttpMethod } from "aws-cdk-lib/aws-events";
import { WebSocketLambdaIntegration } from "aws-cdk-lib/aws-apigatewayv2-integrations";
import * as apigwv2 from "aws-cdk-lib/aws-apigatewayv2";
import * as apigatewayv2_auth from "aws-cdk-lib/aws-apigatewayv2-authorizers"
import * as lambdaNode from "aws-cdk-lib/aws-lambda-nodejs"
import * as elbv2 from "aws-cdk-lib/aws-elasticloadbalancingv2"
import * as elbv2Actions from "aws-cdk-lib/aws-elasticloadbalancingv2-actions";
import * as route53 from "aws-cdk-lib/aws-route53";
/* At present, this repository supports:
 *  "ai21.j2-mid-v1": {},
 *  "ai21.j2-ultra-v1": {},
 *  "amazon.titan-embed-text-v1": {},
 *  "anthropic.claude-v2": {},
 *  "anthropic.claude-v1": {},
 *  "anthropic.claude-instant-v1": {},
 *  "cohere.command-text-v14": {},
 */

export class LlmGatewayStack extends cdk.Stack {
  stackPrefix = "LlmGateway";
  embeddingsModel = "amazon.titan-embed-text-v1";
  chatHistoryTableName = "ChatHistory";

  // Environment variables
  defaultMaxTokens = String(this.node.tryGetContext("maxTokens") || 4096);
  defaultTemp = String(this.node.tryGetContext("defaultTemp") || 0.0);
  hasIamAuth = String(this.node.tryGetContext("useIamAuth")).toLowerCase() == "true";
  regionValue = this.region;
  apiKey = String(this.node.tryGetContext("apiKey"));
  useApiKey = String(this.node.tryGetContext("useApiKey")).toLowerCase() == "true";
  wsEcrRepoName = String(this.node.tryGetContext("ecrWebsocketRepository"));
  opensearchDomainEndpoint = process.env.OPENSEARCH_DOMAIN_ENDPOINT || "";
  vpc = process.env.VPC || null;
  vpcSubnets = process.env.VPC_SUBNETS || null;
  vpcSecurityGroup = process.env.VPC_SECURITY_GROUP || null;
  architecture = this.node.tryGetContext('architecture');
  apiGatewayType = this.node.tryGetContext("apiGatewayType");
  streamlitEcrRepoName = String(this.node.tryGetContext("ecrStreamlitRepository"));
  uiCertArn = String(this.node.tryGetContext("uiCertArn"));
  uiDomainName = String(this.node.tryGetContext("uiDomainName"));

  tryGetParameter(parameterName: string, defaultValue: any = null) {
    const parameter = this.node.tryFindChild(parameterName) as cdk.CfnParameter;
    if (parameter) {
      return parameter.valueAsString;
    } else {
      console.error(`Parameter ${parameterName} not found.`);
      return defaultValue;
    }
  }

  createTokenCountLambda(roleName: string, costTable: dynamodb.Table) {
    // Cerate the IAM role.
    const role = new iam.Role(this, roleName, {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      roleName: roleName,
      inlinePolicies: {
        LambdaPermissions: new iam.PolicyDocument({
          statements: [
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
              resources: [costTable.tableArn],
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

    // Create Lambda function.
    const vpcParams = this.configureVpcParams();
    return new lambda.Function(this, "LlmGatewayTokenCounter", {
      role: role,
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: this.architecture == "x86" ? lambda.Architecture.X86_64 : lambda.Architecture.ARM_64,
      handler: "app.lambda_handler",
      code: lambda.Code.fromAsset(
        path.join(__dirname, "../../lambdas/count_tokens/")
      ),
      environment: {
        COST_TABLE_NAME: costTable.tableName,
      },
      timeout: cdk.Duration.minutes(1),
      ...vpcParams,
    });
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
    if (
      Boolean(this.vpc) &&
      Boolean(this.vpcSubnets) &&
      Boolean(this.vpcSecurityGroup)
    ) {
      console.log(
        "You have configured VPC usage for your Lambdas.\nNote that as of 2023-Dec-18, *API Gateway for WebSockets DOES NOT PROVIDE SUPPORT FOR VPC FEATURES*.\nIf you are configuring a VPC for API Gateway for a REST API, you can ignore this message."
      );
      return {
        vpc: this.vpc,
        vpcSubnets: { subnets: this.vpcSubnets },
        securityGroups: [this.vpcSecurityGroup],
      };
    }
    return {};
  }

  createRestApi(
    chatHistoryTable: dynamodb.Table,
    costLambda: lambda.Function
  ) {
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
        apiKeyName: this.stackPrefix + "ApiKey",
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

    // It's more secure for each lambda to have its own role, despite the clutter.
    const lambdaRole = this.createLlmGatewayLambdaRole(
      "RestLambdaRole",
      api.restApiId,
      chatHistoryTable
    );

    // Create Lambda function from the ECR image.
    const vpcParams = this.configureVpcParams();
    const fn = new lambda.Function(this, "RestLambda", {
      role: lambdaRole,
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: this.architecture == "x86" ? lambda.Architecture.X86_64 : lambda.Architecture.ARM_64,
      handler: "app.lambda_handler",
      code: lambda.Code.fromAsset(
        path.join(__dirname, "../../lambdas/rest/")
      ),
      environment: {
        CHAT_HISTORY_TABLE_NAME: this.chatHistoryTableName,
        DEFAULT_TEMP: this.defaultTemp,
        DEFAULT_MAX_TOKENS: this.defaultMaxTokens,
        REGION: this.regionValue,
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
    const resource = api.root.addResource("RestLambda");
    const authTypes = apigw.AuthorizationType;
    const authType = this.hasIamAuth ? authTypes.IAM : authTypes.NONE;
    resource.addMethod("POST", integration, {
      authorizationType: authType,
      apiKeyRequired: false,
      requestValidator: new apigw.RequestValidator(
        this,
        "RestLambdaBodyValidator",
        {
          restApi: api,
          requestValidatorName: "RestLambdaBodyValidator",
          validateRequestBody: true,
        }
      ),
      requestModels: {
        "application/json": greetModel,
      },
    });
  }

  createWebsocketApi(
    bedrockEcr: ecr.IRepository,
    chatHistoryTable: dynamodb.Table,
    costLambda: lambda.Function
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
      "WebsocketLambda",
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
        architecture: this.architecture == "x86" ? lambda.Architecture.X86_64 : lambda.Architecture.ARM_64,
        environment: {
          CHAT_HISTORY_TABLE_NAME: chatHistoryTable.tableName,
          WEBSOCKET_CONNECTIONS_TABLE_NAME: websocketConnectionsTable.tableName,
          DEFAULT_TEMP: this.defaultTemp,
          DEFAULT_MAX_TOKENS: this.defaultMaxTokens,
          REGION: this.regionValue,
          API_KEY: this.apiKey,
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

    const userPool = new cognito.UserPool(this, "userPool", {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      passwordPolicy: {
        minLength: 8,
        requireDigits: true,
        requireLowercase: false,
        requireUppercase: true,
        requireSymbols: true,
      },
      advancedSecurityMode:cognito.AdvancedSecurityMode.ENFORCED,
    });

    const azureAdDomainPrefix = "llmgatewaymichaeltest123"

    const cognitoDomain = userPool.addDomain('CognitoDomain', {
      cognitoDomain: {
        domainPrefix: azureAdDomainPrefix,
      },
    });

    const applicationLoadBalanceruserPoolClient = new cognito.UserPoolClient(this, 'client', {
      userPoolClientName: 'ApplicationLoadBalancerClient',
      userPool,
      generateSecret: true,
      oAuth: {
        callbackUrls: [`https://${this.uiDomainName}/oauth2/idpresponse`, `https://${this.uiDomainName}/*`],
        flows: {
          authorizationCodeGrant: true
        },
        scopes: [
          cognito.OAuthScope.OPENID,
          cognito.OAuthScope.EMAIL
        ],
      },
      supportedIdentityProviders: [cognito.UserPoolClientIdentityProvider.COGNITO],
    });

    const vpc = new ec2.Vpc(this, 'MyVPC', { });
    const flowLog = new ec2.FlowLog(this, 'FlowLog', {
      resourceType: ec2.FlowLogResourceType.fromVpc(vpc),
      trafficType: ec2.FlowLogTrafficType.ALL,
    });

    // Create ECS Cluster
    const cluster = new ecs.Cluster(this, 'AppCluster', {
      vpc,
      clusterName: 'LlmGatewayUI',
      containerInsights:true,
      
    });

    const logGroup = new logs.LogGroup(this, 'AppLogGroup', {
      logGroupName: '/ecs/LlmGateway/StreamlitUI',
      removalPolicy: cdk.RemovalPolicy.DESTROY
    });

    const ecsExecutionRole = new iam.Role(this, 'EcsExecutionRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      roleName: 'LlmGatewayUIRole'
    });

    ecsExecutionRole.addManagedPolicy(iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AmazonECSTaskExecutionRolePolicy'));

    const stageName = 'prod'; 

    const connectArn = `arn:aws:execute-api:${this.regionValue}:${this.account}:${api.apiId}/${stageName}/$connect`

    const disconnectArn = `arn:aws:execute-api:${this.regionValue}:${this.account}:${api.apiId}/${stageName}/$disconnect`

    const sendMessageArn = `arn:aws:execute-api:${this.regionValue}:${this.account}:${api.apiId}/${stageName}/sendmessage`

    const policyStatement = new iam.PolicyStatement({
      actions: ['execute-api:Invoke'],
      resources: [connectArn, disconnectArn, sendMessageArn],
      effect: iam.Effect.ALLOW
    });

    ecsExecutionRole.addToPolicy(policyStatement);

    const taskDefinition = new ecs.FargateTaskDefinition(this, 'TaskDef', {
      memoryLimitMiB: 512,
      cpu: 256,
      executionRole: ecsExecutionRole,
      taskRole: ecsExecutionRole,
      runtimePlatform: {
        cpuArchitecture: this.architecture == "x86" ? ecs.CpuArchitecture.X86_64 : ecs.CpuArchitecture.ARM64,
      }
    });

    const ecrRepoStreamlit = ecr.Repository.fromRepositoryName(
      this,
      this.streamlitEcrRepoName!,
      this.streamlitEcrRepoName!
    );

    const container = taskDefinition.addContainer('streamlit', {
      image: ecs.ContainerImage.fromEcrRepository(ecrRepoStreamlit, "latest"),
      logging: ecs.LogDrivers.awsLogs({ logGroup, streamPrefix: 'streamlit' }),
      environment: { 
        BASE_URL: 'https://api.example.com', // Should be dynamically set as per your requirements
        API_KEY: 'your-api-key', // Should be securely managed
        WebSocketURL: api.apiEndpoint
      },
      healthCheck: {
        command: ['CMD-SHELL', 'curl -f http://localhost:8501/healthz || exit 1'],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        retries: 3,
        startPeriod: cdk.Duration.seconds(60)
      }
    });

    container.addPortMappings({
      containerPort: 8501,
      hostPort: 8501
    });

    const albSecurityGroup = new ec2.SecurityGroup(this, 'ALBSecurityGroup', {
      securityGroupName: 'LlmGatewayALB-sg',
      vpc,
      allowAllOutbound: true,
    });

    albSecurityGroup.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(80));
    albSecurityGroup.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(443));

    const appSecurityGroup = new ec2.SecurityGroup(this, 'AppSecurityGroup', {
      securityGroupName: 'LlmGatewayUI-sg',
      vpc,
      allowAllOutbound: true,
    });

    appSecurityGroup.addIngressRule(albSecurityGroup, ec2.Port.tcp(8501));

    const service = new ecs.FargateService(this, 'Service', {
      serviceName: "LlmGatewayUI",
      cluster,
      taskDefinition,
      desiredCount: 1,
      securityGroups: [appSecurityGroup],
      assignPublicIp: false,
      circuitBreaker: {
        enable:true,
        rollback:true
      }
    });

    const lb = new elbv2.ApplicationLoadBalancer(this, 'LB', {
      vpc,
      internetFacing: true,
      securityGroup: albSecurityGroup,
    });

    const targetGroup = new elbv2.ApplicationTargetGroup(this, 'AppTG', {
      vpc,
      targetGroupName: 'LlmGatewayUI',
      protocol: elbv2.ApplicationProtocol.HTTP,
      targetType: elbv2.TargetType.IP,
      port: 8501,
      targets: [service]
    });

    const appListener = lb.addListener('appListener', {
      port: 443,
      protocol: elbv2.ApplicationProtocol.HTTPS,
      certificates: [{ certificateArn: this.uiCertArn }],
      defaultAction: elbv2.ListenerAction.fixedResponse(200, {
        contentType: "text/plain",
        messageBody: "This is the default action."
      }),
    });

    const appListener80 = lb.addListener('appListener80', {
      port: 80,
      protocol: elbv2.ApplicationProtocol.HTTP,
      defaultAction: elbv2.ListenerAction.redirect({
        port:"443",
        protocol: "HTTPS",
        permanent: true
      })
    });


    appListener.addAction("authenticate-cognito", {
      priority: 10,
      conditions: [elbv2.ListenerCondition.pathPatterns(["/", "/*"])],
      action: new elbv2Actions.AuthenticateCognitoAction({
        userPool:userPool,
        userPoolClient: applicationLoadBalanceruserPoolClient,
        userPoolDomain: cognitoDomain,
        next: elbv2.ListenerAction.forward([targetGroup])
      })
    });

    const domainParts = this.uiDomainName.split(".");
    const domainName = domainParts.slice(1).join(".");
    const hostName = domainParts[0];

    // Retrieve the existing Route 53 hosted zone
    const hostedZone = route53.HostedZone.fromLookup(this, 'Zone', {
      domainName: `${domainName}.`
    });

    // Create Route 53 A record pointing to the ALB
    new route53.ARecord(this, 'AliasRecord', {
      zone: hostedZone,
      recordName: hostName,
      target: route53.RecordTarget.fromAlias({
        bind: () => ({
          dnsName: lb.loadBalancerDnsName,
          hostedZoneId: lb.loadBalancerCanonicalHostedZoneId,
          evaluateTargetHealth: true,
        })
      })
    });


    // Create endpoints
    api.addRoute("$connect", {
      integration: new WebSocketLambdaIntegration("ConnectIntegration", fn),
      authorizer: new apigatewayv2_auth.WebSocketIamAuthorizer
    });
    api.addRoute("$disconnect", {
      integration: new WebSocketLambdaIntegration("DisconnectIntegration", fn),
    });
    api.addRoute("sendmessage", {
      integration: new WebSocketLambdaIntegration("SendMessageIntegration", fn),
    });

    // Output the User Pool ID
    new cdk.CfnOutput(this, 'UserPoolId', {
      value: userPool.userPoolId,
      description: 'The ID of the User Pool',
    });

    // Output the User Pool Client ID
    new cdk.CfnOutput(this, 'UserPoolClientId', {
      value: applicationLoadBalanceruserPoolClient.userPoolClientId,
      description: 'The ID of the User Pool Client',
    });

    new cdk.CfnOutput(this, 'WebSocketUrl', {
      value: api.apiEndpoint,
      description: 'WebSocket URL for the API Gateway',
    });

    new cdk.CfnOutput(this, 'WebSocketLambdaFunctionName', {
      value: fn.functionName,
      description: 'Name of the websocket lambda function'
    });

    new cdk.CfnOutput(this, 'StreamlitUiUrl', {
      value: "https://" + this.uiDomainName,
      description: 'The url of the streamlit UI'
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
      this.chatHistoryTableName,
      "id"
    );

    // Create a table for storing costs of using different LLMs.
    const costTable = this.createSecureDdbTable("CostTable", "id");
    const costLambda = this.createTokenCountLambda("CostLambda", costTable);

    if (this.apiGatewayType == "rest") {
      // Assuming you have an existing ECR repository.
      const api = this.createRestApi(chatHistoryTable, costLambda);
    } else if (this.apiGatewayType == "websocket") {
      // Assuming you have an existing ECR repository.
      const ecrRepo = ecr.Repository.fromRepositoryName(
        this,
        this.wsEcrRepoName!,
        this.wsEcrRepoName!
      );
      const api = this.createWebsocketApi(
        ecrRepo,
        chatHistoryTable,
        costLambda
      );
    } else {
      throw Error(
        `apiGatewayType must be set to either "rest" or "websocket"`
      );
    }
  }
}
