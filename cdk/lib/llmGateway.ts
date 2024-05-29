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
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';

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
  useApiKey = String(this.node.tryGetContext("useApiKey")).toLowerCase() == "true";
  opensearchDomainEndpoint = process.env.OPENSEARCH_DOMAIN_ENDPOINT || "";
  vpc = process.env.VPC || null;
  vpcSubnets = process.env.VPC_SUBNETS || null;
  vpcSecurityGroup = process.env.VPC_SECURITY_GROUP || null;
  architecture = this.node.tryGetContext('architecture');
  apiGatewayType = this.node.tryGetContext("apiGatewayType");
  streamlitEcrRepoName = String(this.node.tryGetContext("ecrStreamlitRepository"));
  uiCertArn = String(this.node.tryGetContext("uiCertArn"));
  uiDomainName = String(this.node.tryGetContext("uiDomainName"));
  metadataURLCopiedFromAzureAD = this.node.tryGetContext("metadataURLCopiedFromAzureAD");
  gitHubClientId = this.node.tryGetContext("gitHubClientId");
  gitHubClientSecret = this.node.tryGetContext("gitHubClientSecret");
  gitHubProxyUrl = this.node.tryGetContext("gitHubProxyUrl");
  cognitoDomainPrefix = this.node.tryGetContext("cognitoDomainPrefix");
  openaiApiKey = String(this.node.tryGetContext("openaiApiKey"));
  googleApiKey = this.node.tryGetContext("googleApiKey");
  anthropicApiKey = this.node.tryGetContext("anthropicApiKey");
  azureOpenaiEndpoint = this.node.tryGetContext("azureOpenaiEndpoint");
  azureOpenaiApiKey = this.node.tryGetContext("azureOpenaiApiKey");
  azureOpenaiApiVersion = this.node.tryGetContext("azureOpenaiApiVersion");
  apiKeyEcrRepoName = this.node.tryGetContext("apiKeyEcrRepoName");
  salt = this.node.tryGetContext("salt");
  llmGatewayRepoName = this.node.tryGetContext("llmGatewayRepoName");

  apiKeyValueHashIndex = "ApiKeyValueHashIndex"
  apiKeyTableName = "ApiKeyTable"
  apiKeyTablePartitionKey = "username"
  apiKeyTableSortKey = "api_key_name"
  apiKeyTableIndexPartitionKey = "api_key_value_hash"
  apiKeyHandlerFunctionName = "apiKeyHandlerFunction";

  userPool: cognito.IUserPool;
  authHandler: lambda.IFunction;
  applicationLoadBalanceruserPoolClient: cognito.IUserPoolClient;
  cognitoDomain: cognito.IUserPoolDomain
  provider: cognito.UserPoolClientIdentityProvider;

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

  createSecureDdbTableWithSortKey(
    tableName: string,
    partitionKeyName: string,
    sortKeyName: string,
    secondaryIndexName: string,
    secondaryIndexPartitionKeyName: string
  ) {
    const table = new dynamodb.Table(this, tableName, {
      partitionKey: {
        name: partitionKeyName,
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: {
        name: sortKeyName,
        type: dynamodb.AttributeType.STRING,
      },
      encryption: dynamodb.TableEncryption.AWS_MANAGED,
      pointInTimeRecovery: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Adding a Global Secondary Index for the secondary index using provided parameters
    table.addGlobalSecondaryIndex({
      indexName: secondaryIndexName,
      partitionKey: {
        name: secondaryIndexPartitionKeyName,
        type: dynamodb.AttributeType.STRING,
      },
      projectionType: dynamodb.ProjectionType.ALL, // Determines which attributes will be copied to the index
    });

    return table;
  };


  createLlmGatewayLambdaRole(
    roleName: string,
    apiId: string,
    chatHistoryTable: dynamodb.Table,
    apiKeyTable: dynamodb.Table,
    apiKeyValueHashIndex: string,
    secret: secretsmanager.Secret
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
              resources: [chatHistoryTable.tableArn, apiKeyTable.tableArn, `${apiKeyTable.tableArn}/index/${apiKeyValueHashIndex}`],
            }),
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret"
              ],
              resources: [secret.secretArn]  // Restrict policy to this specific secret
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

  createApiKeyLambdaRole(
    roleName: string, 
    apiKeyTable: dynamodb.ITable,
    apiKeyValueHashIndex: string,
    secret: secretsmanager.ISecret
  ) {
    return new iam.Role(this, roleName, {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      roleName: roleName,
      inlinePolicies: {
        LambdaPermissions: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              sid: "ApiKeyDynamoDBAccess",
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
              resources: [apiKeyTable.tableArn, `${apiKeyTable.tableArn}/index/${apiKeyValueHashIndex}`],
            }),
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret"
              ],
              resources: [secret.secretArn]  // Restrict policy to this specific secret
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
          ]
        })
      }
    })
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
    costLambda: lambda.Function,
    apiKeyEcr: ecr.IRepository,
    restApiEcr: ecr.IRepository
  ) {
    const saltSecret = this.createSaltSecret()

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
    }

    const apiKeyTable = this.createSecureDdbTableWithSortKey(
      this.apiKeyTableName,
      this.apiKeyTablePartitionKey,
      this.apiKeyTableSortKey,
      this.apiKeyValueHashIndex, 
      this.apiKeyTableIndexPartitionKey
    )

    const lambdaRole = this.createLlmGatewayLambdaRole(
      "RestLambdaRole",
      api.restApiId,
      chatHistoryTable,
      apiKeyTable,
      this.apiKeyValueHashIndex,
      saltSecret
    );

    // Create Lambda function from the ECR image.
    const vpcParams = this.configureVpcParams();
    const fn = new lambda.DockerImageFunction(this, "RestLambda", {
      code: lambda.DockerImageCode.fromEcr(restApiEcr, { tag: "latest" }),
      role: lambdaRole,
      architecture: this.architecture == "x86" ? lambda.Architecture.X86_64 : lambda.Architecture.ARM_64,
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


    this.setUpCognito(saltSecret, apiKeyTable)

    const authorizerName = "Authorizer";
    const apiAuthorizer = new apigw.TokenAuthorizer(this,
      authorizerName,
      {
        handler: this.authHandler,
        identitySource: "method.request.header.Authorization",
      },
    )

    const apiKeyApi = this.createApiKeyHandlerApi(apiKeyTable, saltSecret, vpcParams, apiKeyEcr)

    this.setUpStreamlit(api.url, apiKeyApi)

    // Create a resource and associate the Lambda integration
    const resource = api.root.addResource("RestLambda");
    resource.addMethod("POST", new apigw.LambdaIntegration(fn, { proxy: true,}), {
      authorizer: apiAuthorizer,
    });

    new cdk.CfnOutput(this, "output" + this.stackPrefix + "Api", {
      value: api.url,
    });

    new cdk.CfnOutput(this, 'LlmgatewayLambdaFunctionName', {
      value: fn.functionName,
      description: 'Name of the llmgateway rest lambda function'
    });
  }

  createSaltSecret() : secretsmanager.Secret {
    return new secretsmanager.Secret(this, 'MySaltSecret', {
      generateSecretString: {
        secretStringTemplate: JSON.stringify({ salt: this.salt }),
        generateStringKey: 'dummyKey'  // Required by AWS but not used since we provide the complete template
      }
    });
  }

  createApiKeyHandlerApi(apiKeyTable: dynamodb.ITable, saltSecret: secretsmanager.ISecret, vpcParams: object, apiKeyEcr: ecr.IRepository) : apigw.RestApi {
    const apiKeyAuthorizerGet = new apigw.TokenAuthorizer(this,
      "ApiKeyAuthorizerGet",
      {
        handler: this.authHandler,
        identitySource: "method.request.header.Authorization",
      },
    )

    const apiKeyAuthorizerPost = new apigw.TokenAuthorizer(this,
      "ApiKeyAuthorizerPost",
      {
        handler: this.authHandler,
        identitySource: "method.request.header.Authorization",
      },
    )

    const apiKeyAuthorizerDelete = new apigw.TokenAuthorizer(this,
      "ApiKeyAuthorizerDelete",
      {
        handler: this.authHandler,
        identitySource: "method.request.header.Authorization",
      },
    )

    const apiKeyapi = new apigw.RestApi(this, "LlmGatewayApiKey", {
      defaultCorsPreflightOptions: {
        allowOrigins: apigw.Cors.ALL_ORIGINS,
        allowMethods: apigw.Cors.ALL_METHODS,  // Make sure POST is included
        allowHeaders: ['Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Amz-User-Agent'],
        allowCredentials: true,
      },
    });

    const apiKeyHandler = new lambda.DockerImageFunction(this, 'apiKeyHandler', {
      functionName: this.apiKeyHandlerFunctionName,
      code: lambda.DockerImageCode.fromEcr(apiKeyEcr, { tag: "latest" }),
      role: this.createApiKeyLambdaRole("apiKeyHandlerRole", apiKeyTable, this.apiKeyValueHashIndex, saltSecret),
      architecture: this.architecture == "x86" ? lambda.Architecture.X86_64 : lambda.Architecture.ARM_64,
      environment: {
        API_KEY_TABLE_NAME: apiKeyTable.tableName,
        COGNITO_DOMAIN_PREFIX: this.cognitoDomainPrefix,
        REGION: this.regionValue,
        SALT_SECRET: saltSecret.secretName
      },
      timeout: cdk.Duration.minutes(15),
      memorySize: 512,
      ...vpcParams,
    });

    const apiKeyResource = apiKeyapi.root.addResource('apikey');

    // Add GET endpoint
    apiKeyResource.addMethod('GET', new apigw.LambdaIntegration(apiKeyHandler), {
      authorizer: apiKeyAuthorizerGet
    });

    // Add POST endpoint
    apiKeyResource.addMethod('POST', new apigw.LambdaIntegration(apiKeyHandler), {
      authorizer: apiKeyAuthorizerPost
    });

    // Add DELETE endpoint
    apiKeyResource.addMethod('DELETE', new apigw.LambdaIntegration(apiKeyHandler), {
      authorizer: apiKeyAuthorizerDelete
    });

    new cdk.CfnOutput(this, 'ApiKeyLambdaFunctionName', {
      value: this.apiKeyHandlerFunctionName,
      description: 'Name of the api key lambda function'
    });

    return apiKeyapi
  }

  setUpCognito(saltSecret: secretsmanager.ISecret, apiKeyTable: dynamodb.ITable) {
    let signInAliases = this.metadataURLCopiedFromAzureAD ? { email: true } : { username: true, email: true }
        this.userPool = new cognito.UserPool(this, "userPool", {
          removalPolicy: cdk.RemovalPolicy.DESTROY,
          passwordPolicy: {
            minLength: 8,
            requireDigits: true,
            requireLowercase: false,
            requireUppercase: true,
            requireSymbols: true,
          },
          advancedSecurityMode:cognito.AdvancedSecurityMode.ENFORCED,
          selfSignUpEnabled: false,
          autoVerify: { email: true},
          signInAliases: signInAliases,
          customAttributes: {
            azureAdCustom: new cognito.StringAttribute({ mutable: true })
          },
        });

        let provider = cognito.UserPoolClientIdentityProvider.COGNITO;
        if (this.metadataURLCopiedFromAzureAD) {
          let azureAdProvider = new cognito.UserPoolIdentityProviderSaml(this, 'MySamlProvider', {
            userPool: this.userPool,
            name: "Azure-AD",
            metadata: cognito.UserPoolIdentityProviderSamlMetadata.url(this.metadataURLCopiedFromAzureAD), // Metadata document or URL
            attributeMapping: {
              // Map attributes from SAML token to Cognito user pool attributes
              email: cognito.ProviderAttribute.other('http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress'),
              custom: {
                "custom:azureAdCustom": cognito.ProviderAttribute.other("http://schemas.microsoft.com/ws/2008/06/identity/claims/groups")
              }
            }
          });
          provider = cognito.UserPoolClientIdentityProvider.custom(azureAdProvider.providerName)
        } else if(this.gitHubClientId && this.gitHubClientSecret) {
            let gitHubProvider = new cognito.UserPoolIdentityProviderOidc(this, 'MyGitHubProvider', {
              userPool: this.userPool,
              name: "GitHub",
              clientId: this.gitHubClientId,
              clientSecret: this.gitHubClientSecret,
              attributeRequestMethod: cognito.OidcAttributeRequestMethod.GET,
              issuerUrl: this.gitHubProxyUrl,
              scopes: ['openid', 'user'],
              endpoints: {
                authorization: this.gitHubProxyUrl.concat('/authorize'),
                token: this.gitHubProxyUrl.concat('/token'),
                userInfo: this.gitHubProxyUrl.concat('/userinfo'),
                jwksUri: this.gitHubProxyUrl.concat('/.well-known/jwks.json')
              },
              attributeMapping: {
                custom: {
                  "username": cognito.ProviderAttribute.other("sub"),
                  "email_verified": cognito.ProviderAttribute.other("email_verified"),
                },
                email: cognito.ProviderAttribute.other("email"),
                fullname: cognito.ProviderAttribute.other('name'),
                profilePicture: cognito.ProviderAttribute.other('picture'),
                preferredUsername: cognito.ProviderAttribute.other("preferred_username"),
                profilePage: cognito.ProviderAttribute.other("profile"),
                lastUpdateTime: cognito.ProviderAttribute.other("updated_at"),
                website: cognito.ProviderAttribute.other("website"),
              }
            }
          )
          provider = cognito.UserPoolClientIdentityProvider.custom(gitHubProvider.providerName)
        }

        this.cognitoDomain = this.userPool.addDomain('CognitoDomain', {
          cognitoDomain: {
            domainPrefix: this.cognitoDomainPrefix,
          },
        });

        this.applicationLoadBalanceruserPoolClient = new cognito.UserPoolClient(this, 'client', {
          userPoolClientName: 'ApplicationLoadBalancerClient',
          userPool: this.userPool,
          generateSecret: true,
          oAuth: {
            callbackUrls: [`https://${this.uiDomainName}/oauth2/idpresponse`, `https://${this.uiDomainName}/`],
            flows: {
              authorizationCodeGrant: true
            },
            scopes: [
              cognito.OAuthScope.OPENID,
              cognito.OAuthScope.EMAIL
            ],
          },
          supportedIdentityProviders: [
            provider
          ],
          enableTokenRevocation: true,
        });

        this.authHandler = new lambdaNode.NodejsFunction(this, "AuthHandlerFunction", {
          runtime: lambda.Runtime.NODEJS_20_X,
          entry: path.join(__dirname, "authorizers/websocket/index.ts"),
          architecture: this.architecture == "x86" ? lambda.Architecture.X86_64 : lambda.Architecture.ARM_64,
          environment: {
            USER_POOL_ID: this.userPool.userPoolId,
            APP_CLIENT_ID: this.applicationLoadBalanceruserPoolClient.userPoolClientId,
            API_KEY_TABLE_NAME: this.apiKeyTableName,
            SALT_SECRET: saltSecret.secretName
          },
          bundling: {
            minify: false,
          },
          role: new iam.Role(this, "AuthHandlerRole", {
            assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
            roleName: "AuthHandlerRole",
            inlinePolicies: {
              LambdaPermissions: new iam.PolicyDocument({
                statements: [
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
                  new iam.PolicyStatement({
                    sid: "ApiKeyDynamoDBAccess",
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
                    resources: [apiKeyTable.tableArn, `${apiKeyTable.tableArn}/index/${this.apiKeyValueHashIndex}`],
                  }),
                  new iam.PolicyStatement({
                    effect: iam.Effect.ALLOW,
                    actions: [
                      "secretsmanager:GetSecretValue",
                      "secretsmanager:DescribeSecret"
                    ],
                    resources: [saltSecret.secretArn]  // Restrict policy to this specific secret
                  }),
                ],
              }),
            },
          })
        });

        new cdk.CfnOutput(this, 'provider', {
          value: provider.name,
          description: 'The chosen provider'
        });

         // Output the User Pool ID
        new cdk.CfnOutput(this, 'UserPoolId', {
          value: this.userPool.userPoolId,
          description: 'The ID of the User Pool',
        });

        // Output the User Pool Client ID
        new cdk.CfnOutput(this, 'UserPoolClientId', {
          value: this.applicationLoadBalanceruserPoolClient.userPoolClientId,
          description: 'The ID of the User Pool Client',
        });

        // Output the domain URL
        new cdk.CfnOutput(this, 'UserPoolDomain', {
          value: `https://${this.cognitoDomainPrefix}.auth.${this.regionValue}.amazoncognito.com`,
        });

        const entityId = `urn:amazon:cognito:sp:${this.userPool.userPoolId}`;

        // Output the Identifier (Entity ID)
        new cdk.CfnOutput(this, 'EntityId', {
          value: entityId,
        });

        // Reply URL for the SAML provider
        const replyUrl = `https://${this.cognitoDomainPrefix}.auth.${this.regionValue}.amazoncognito.com/saml2/idpresponse`;

        // Output the Reply URL
        new cdk.CfnOutput(this, 'ReplyURL', {
          value: replyUrl,
        });

        new cdk.CfnOutput(this, 'CustomAttributeName', {
          value: "azureAdCustom",
        });
  }

  setUpStreamlit(apiUrl: string, apiKeyApi: apigw.RestApi) {
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
        //Could be websocket or rest. Streamlit code will look at the url and behave accordingly
        ApiUrl: apiUrl,
        ApiKeyURL: apiKeyApi.url
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
        userPool:this.userPool,
        userPoolClient: this.applicationLoadBalanceruserPoolClient,
        userPoolDomain: this.cognitoDomain,
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

    new cdk.CfnOutput(this, 'StreamlitUiUrl', {
      value: "https://" + this.uiDomainName,
      description: 'The url of the streamlit UI'
    });
  }

  createWebsocketApi(
    bedrockEcr: ecr.IRepository,
    apiKeyEcr: ecr.IRepository,
    chatHistoryTable: dynamodb.Table,
    costLambda: lambda.Function
  ) {
    const saltSecret = this.createSaltSecret()
    
    const api = new apigwv2.WebSocketApi(this, "LlmGatewayWebsocket");

    const stage = new apigwv2.WebSocketStage(this, "prod", {
      webSocketApi: api,
      stageName: "prod",
      autoDeploy: true
    });

    //Cfn resources needed for usage plan because of lack of CDK support: https://github.com/aws/aws-cdk/issues/28756
    if(this.useApiKey) {
      const cfnApiKey = new apigw.CfnApiKey(this, 'llmGatewayApiKey', {
        description: 'test api key for usage plan',
        enabled: true,
        name: 'llmGatewayApiKey',
      });
    
      const cfnUsagePlan = new apigw.CfnUsagePlan(this, 'llmGatewayUsagePlan', {
          apiStages: [{
              apiId: api.apiId,
              stage: stage.stageName,
          }],
          description: 'description',
          usagePlanName: 'llmGatewayUsagePlan'
      });
      
      const cfnUsagePlanKey = new apigw.CfnUsagePlanKey(this, 'MyCfnUsagePlanKey', {
          keyId: cfnApiKey.attrApiKeyId,
          keyType: 'API_KEY',
          usagePlanId: cfnUsagePlan.attrId
      });
    }

    // Create a connections table.
    const websocketConnectionsTableName = "WebsocketConnections";
    const websocketConnectionsTable = this.createSecureDdbTable(
      websocketConnectionsTableName,
      "connection_id"
    );

    const apiKeyTable = this.createSecureDdbTableWithSortKey(
      this.apiKeyTableName,
      this.apiKeyTablePartitionKey,
      this.apiKeyTableSortKey,
      this.apiKeyValueHashIndex, 
      this.apiKeyTableIndexPartitionKey
    )

    const lambdaRole = this.createLlmGatewayLambdaRole(
      "WebsocketLambda",
      api.apiId,
      chatHistoryTable,
      apiKeyTable,
      this.apiKeyValueHashIndex,
      saltSecret
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
          EMBEDDINGS_MODEL: this.embeddingsModel,
          OPENSEARCH_DOMAIN_ENDPOINT: this.opensearchDomainEndpoint,
          OPENSEARCH_INDEX: "llm-rag-hackathon",
          OPENAI_API_KEY: this.openaiApiKey,
          GOOGLE_API_KEY: this.googleApiKey,
          ANTHROPIC_API_KEY: this.anthropicApiKey,
          AZURE_OPENAI_ENDPOINT: this.azureOpenaiEndpoint,
          AZURE_OPENAI_API_KEY: this.azureOpenaiApiKey,
          OPENAI_API_VERSION: this.azureOpenaiApiVersion,
          COGNITO_DOMAIN_PREFIX: this.cognitoDomainPrefix,
          API_KEY_TABLE_NAME: apiKeyTable.tableName,
          SALT_SECRET: saltSecret.secretName
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

    this.setUpCognito(saltSecret, apiKeyTable)

    const authorizer = new apigatewayv2_auth.WebSocketLambdaAuthorizer(
      "Authorizer",
      this.authHandler,
      {
        identitySource: ["route.request.header.Authorization"],
      },
    );

    const apiKeyApi = this.createApiKeyHandlerApi(apiKeyTable, saltSecret, vpcParams, apiKeyEcr)

    this.setUpStreamlit(api.apiEndpoint, apiKeyApi)

    // Create endpoints
    api.addRoute("$connect", {
      integration: new WebSocketLambdaIntegration("ConnectIntegration", fn),
      authorizer: authorizer
    });
    api.addRoute("$disconnect", {
      integration: new WebSocketLambdaIntegration("DisconnectIntegration", fn),
    });
    api.addRoute("sendmessage", {
      integration: new WebSocketLambdaIntegration("SendMessageIntegration", fn),
    });

    new cdk.CfnOutput(this, 'WebSocketUrl', {
      value: api.apiEndpoint,
      description: 'WebSocket URL for the API Gateway',
    });

    new cdk.CfnOutput(this, 'LlmgatewayLambdaFunctionName', {
      value: fn.functionName,
      description: 'Name of the llmgateway rest lambda function'
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
    const apiKeyEcrRepo = ecr.Repository.fromRepositoryName(
      this,
      this.apiKeyEcrRepoName!,
      this.apiKeyEcrRepoName!
    );

    const llmGatewayEcrRepoName = ecr.Repository.fromRepositoryName(
      this,
      this.llmGatewayRepoName!,
      this.llmGatewayRepoName!
    );

    if (this.apiGatewayType == "rest") {
      const api = this.createRestApi(chatHistoryTable, costLambda, apiKeyEcrRepo, llmGatewayEcrRepoName);
    } else if (this.apiGatewayType == "websocket") {
      const api = this.createWebsocketApi(
        llmGatewayEcrRepoName,
        apiKeyEcrRepo,
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
