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
import * as targets from 'aws-cdk-lib/aws-elasticloadbalancingv2-targets';
import * as ssm from "aws-cdk-lib/aws-ssm";
import * as lambdaPython from '@aws-cdk/aws-lambda-python-alpha'

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
  regionValue = this.region;
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
  apiKeyEcrRepoName = this.node.tryGetContext("apiKeyEcrRepoName");
  salt = this.node.tryGetContext("salt");
  llmGatewayRepoName = this.node.tryGetContext("llmGatewayRepoName");
  llmGatewayCertArn = String(this.node.tryGetContext("llmGatewayCertArn"));
  llmGatewayDomainName = String(this.node.tryGetContext("llmGatewayDomainName"));
  llmGatewayIsPublic = String(this.node.tryGetContext("llmGatewayIsPublic")).toLowerCase() == "true";
  serverlessApi = String(this.node.tryGetContext("serverlessApi")).toLowerCase() == "true";
  defaultQuotaFrequency = String(this.node.tryGetContext("defaultQuotaFrequency"));
  defaultQuotaDollars = String(this.node.tryGetContext("defaultQuotaDollars"));
  quotaRepoName = this.node.tryGetContext("quotaRepoName");
  adminList = this.node.tryGetContext("adminList");
  defaultModelAccess = this.node.tryGetContext("defaultModelAccess");
  modelAccessRepoName = this.node.tryGetContext("modelAccessRepoName");
  debug = this.node.tryGetContext("debug");

  apiKeyValueHashIndex = "ApiKeyValueHashIndex";
  apiKeyTableName = "ApiKeyTable";
  apiKeyTablePartitionKey = "username";
  apiKeyTableSortKey = "api_key_name";
  apiKeyTableIndexPartitionKey = "api_key_value_hash";
  apiKeyHandlerFunctionName = "apiKeyHandlerFunction";
  quotaTableName = "QuotaTable";
  quotaTablePartitionKey = "username";
  quotaTableSortKey = "document_type_id";
  quotaHandlerFunctionName = "quotaHandlerFunciton";
  modelAccessTableName = "ModelAccessTable";
  modelAccessTablePartitionKey = "username";
  modelAccessHandlerFunctionName = "modelAccessHandlerFunciton";
  requestDetailsTableName = "RequestDetailsTable";
  requestDetailsTablePartitionKey = "username";
  requestDetailsTableSortKey = "timestamp";

  nonAdminEndpoints = "/apikey,/quota/currentusersummary,/modelaccess/currentuser"
  apiKeyExcludedEndpoints = "/apikey"

  userPool: cognito.IUserPool;
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
    secondaryIndexName: string | null,
    secondaryIndexPartitionKeyName: string | null
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

    if (secondaryIndexName && secondaryIndexPartitionKeyName) {
      // Adding a Global Secondary Index for the secondary index using provided parameters
      table.addGlobalSecondaryIndex({
        indexName: secondaryIndexName,
        partitionKey: {
          name: secondaryIndexPartitionKeyName,
          type: dynamodb.AttributeType.STRING,
        },
        projectionType: dynamodb.ProjectionType.ALL, // Determines which attributes will be copied to the index
      });
    }

    return table;
  };

  createLlmGatewayRole(
    roleName: string,
    chatHistoryTable: dynamodb.Table,
    quotaTable: dynamodb.Table,
    modelAccessTable: dynamodb.Table,
    requestDetailsTable: dynamodb.Table,
    apiKeyTable: dynamodb.Table,
    apiKeyValueHashIndex: string,
    secret: secretsmanager.Secret,
    defaultQuotaParameter: ssm.StringParameter,
    defaultModelAccessParameter: ssm.StringParameter,
    assumedBy: iam.ServicePrincipal
  ) {
    const resourceArn = null;
    return new iam.Role(this, roleName, {
      assumedBy: assumedBy,
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
              resources: [chatHistoryTable.tableArn, apiKeyTable.tableArn, `${apiKeyTable.tableArn}/index/${apiKeyValueHashIndex}`, quotaTable.tableArn, modelAccessTable.tableArn, requestDetailsTable.tableArn],
            }),
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret"
              ],
              resources: [secret.secretArn]
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
            new iam.PolicyStatement({
              actions: ['ssm:GetParameter'],
              resources: [defaultQuotaParameter.parameterArn],
              effect: iam.Effect.ALLOW
            }),
            new iam.PolicyStatement({
              actions: ['ssm:GetParameter'],
              resources: [defaultModelAccessParameter.parameterArn],
              effect: iam.Effect.ALLOW
            })
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

  createQuotaLambdaRole(
    roleName: string, 
    quotaTable: dynamodb.ITable,
    defaultQuotaParameter:ssm.StringParameter,
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
              resources: [quotaTable.tableArn, apiKeyTable.tableArn, `${apiKeyTable.tableArn}/index/${apiKeyValueHashIndex}`],
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
            new iam.PolicyStatement({
              actions: ['ssm:GetParameter'],
              resources: [defaultQuotaParameter.parameterArn],
              effect: iam.Effect.ALLOW
            })
          ]
        })
      }
    })
  }

  createModelAccessLambdaRole(
    roleName: string, 
    modelAccessTable: dynamodb.ITable,
    defaultModelAccessParameter:ssm.StringParameter,
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
              resources: [modelAccessTable.tableArn, apiKeyTable.tableArn, `${apiKeyTable.tableArn}/index/${apiKeyValueHashIndex}`],
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
            new iam.PolicyStatement({
              actions: ['ssm:GetParameter'],
              resources: [defaultModelAccessParameter.parameterArn],
              effect: iam.Effect.ALLOW
            })
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

  createEcsTargetGroup(vpc: ec2.Vpc, service: ecs.FargateService, type: string) : elbv2.ApplicationTargetGroup {
    return new elbv2.ApplicationTargetGroup(this, 'llmGatewayEcsTargetGroup' + type, {
      vpc,
      targetGroupName: 'llmGatewayEcsTargetGroup' + type,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targetType: elbv2.TargetType.IP,
      port: 80,
      targets: [service],
      healthCheck: {
        enabled: true,
        path: "/health"
      }
    });
  }

  createAlbApi(
    chatHistoryTable: dynamodb.Table,
    apiKeyEcr: ecr.IRepository,
    llmGatewayApiEcr: ecr.IRepository,
    quotaEcr: ecr.IRepository,
    modelAccessEcr: ecr.IRepository
  ) {
    let parameterValue: { [key: string]: string } = {};
    parameterValue[this.defaultQuotaFrequency] = this.defaultQuotaDollars;

    // Serialize the map to a JSON string
    const parameterValueString = JSON.stringify(parameterValue);

    // Store the serialized map in SSM Parameter Store
    const defaultQuotaParameter = new ssm.StringParameter(this, 'MyParameter', {
      parameterName: 'defaultQuota',
      stringValue: parameterValueString,
      description: 'This parameter stores the default quota for users',
      tier: ssm.ParameterTier.STANDARD
    });

    let parameterValueDefaultModelAccess = {
      "model_access_list": this.defaultModelAccess
    }
    const parameterValueDefaultModelAccessString = JSON.stringify(parameterValueDefaultModelAccess);

    // Store the serialized map in SSM Parameter Store
    const defaultModelAccessParameter = new ssm.StringParameter(this, 'DefaultModelAccessParameter', {
      parameterName: 'defaultModelAccess',
      stringValue: parameterValueDefaultModelAccessString,
      description: 'This parameter stores the default model access for users',
      tier: ssm.ParameterTier.STANDARD
    });

    const modelAccessTable = this.createSecureDdbTable(
      this.modelAccessTableName,
      this.modelAccessTablePartitionKey,
    )

    const quotaTable = this.createSecureDdbTableWithSortKey(
      this.quotaTableName,
      this.quotaTablePartitionKey,
      this.quotaTableSortKey,
      null,
      null
    )

    const requestDetailsTable = this.createSecureDdbTableWithSortKey(
      this.requestDetailsTableName,
      this.requestDetailsTablePartitionKey,
      this.requestDetailsTableSortKey,
      null,
      null
    )

    const saltSecret = this.createSaltSecret()

    const apiKeyTable = this.createSecureDdbTableWithSortKey(
      this.apiKeyTableName,
      this.apiKeyTablePartitionKey,
      this.apiKeyTableSortKey,
      this.apiKeyValueHashIndex, 
      this.apiKeyTableIndexPartitionKey
    )

    this.setUpCognito()

    const vpc = new ec2.Vpc(this, 'MyVPC', { });
    const flowLog = new ec2.FlowLog(this, 'FlowLog', {
      resourceType: ec2.FlowLogResourceType.fromVpc(vpc),
      trafficType: ec2.FlowLogTrafficType.ALL,
    });


    // Create Lambda function from the ECR image.
    const vpcParams = this.configureVpcParams();
    let targetGroupLlmGateway :elbv2.ApplicationTargetGroup;

    const environment = {
      CHAT_HISTORY_TABLE_NAME: chatHistoryTable.tableName,
      REGION: this.regionValue,
      COGNITO_DOMAIN_PREFIX: this.cognitoDomainPrefix,
      API_KEY_TABLE_NAME: apiKeyTable.tableName,
      SALT_SECRET: saltSecret.secretName,
      USER_POOL_ID: this.userPool.userPoolId,
      APP_CLIENT_ID: this.applicationLoadBalanceruserPoolClient.userPoolClientId,
      QUOTA_TABLE_NAME: quotaTable.tableName,
      MODEL_ACCESS_TABLE_NAME: modelAccessTable.tableName,
      DEFAULT_QUOTA_PARAMETER_NAME: defaultQuotaParameter.parameterName,
      DEFAULT_MODEL_ACCESS_PARAMETER_NAME: defaultModelAccessParameter.parameterName,
      REQUEST_DETAILS_TABLE_NAME: requestDetailsTable.tableName,
      DEBUG: this.debug
    }

    // Create a Security Group for the private ALB that only allows traffic from within the VPC
    const llmGatewayAlbSecurityGroup = new ec2.SecurityGroup(this, 'LlmGatewayAlbSecurityGroup', {
      vpc,
      description: 'Security group for llmgateway ALB',
      allowAllOutbound: true,
    });

    if (this.llmGatewayIsPublic) {
      llmGatewayAlbSecurityGroup.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(80));
      llmGatewayAlbSecurityGroup.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(443));
    }

    const llmGatewayEcsCluster = "LlmGateway"
    const cluster = new ecs.Cluster(this, 'AppCluster', {
      vpc,
      clusterName: llmGatewayEcsCluster,
      containerInsights:true,
      
    });

    new cdk.CfnOutput(this, 'LlmgatewayEcsCluster', {
      value: llmGatewayEcsCluster,
      description: 'Name of the llmgateway ecs cluster'
    });

    if (this.serverlessApi) {
      const lambdaRole = this.createLlmGatewayRole(
        "llmGatewayLambdaRole",
        chatHistoryTable,
        quotaTable,
        modelAccessTable,
        requestDetailsTable,
        apiKeyTable,
        this.apiKeyValueHashIndex,
        saltSecret,
        defaultQuotaParameter,
        defaultModelAccessParameter,
        new iam.ServicePrincipal("lambda.amazonaws.com")
      )
      const fn = new lambda.DockerImageFunction(this, "llmGatewayLambda", {
        code: lambda.DockerImageCode.fromEcr(llmGatewayApiEcr, { tag: "latest" }),
        role: lambdaRole,
        architecture: this.architecture == "x86" ? lambda.Architecture.X86_64 : lambda.Architecture.ARM_64,
        environment: environment,
        timeout: cdk.Duration.minutes(15),
        memorySize: 512,
        ...vpcParams,
      });

      //Create a target group for the Lambda function
      targetGroupLlmGateway = new elbv2.ApplicationTargetGroup(this, 'LambdaTargetGroup', {
        vpc,
        targetType: elbv2.TargetType.LAMBDA,
        targets: [new targets.LambdaTarget(fn)],
      });

      new cdk.CfnOutput(this, 'LlmgatewayLambdaFunctionName', {
        value: fn.functionName,
        description: 'Name of the llmgateway alb lambda function'
      });
    }
    else {
      const llmGatewayEcsTask = "LlmGatewayApi"

      const logGroup = new logs.LogGroup(this, 'llmGatewayLogGroup', {
        logGroupName: '/ecs/LlmGateway/Api',
        removalPolicy: cdk.RemovalPolicy.DESTROY
      });

      const ecsExecutionRole = this.createLlmGatewayRole(
        "llmGatewayEcsRole",
        chatHistoryTable,
        quotaTable,
        modelAccessTable,
        requestDetailsTable,
        apiKeyTable,
        this.apiKeyValueHashIndex,
        saltSecret,
        defaultQuotaParameter,
        defaultModelAccessParameter,
        new iam.ServicePrincipal('ecs-tasks.amazonaws.com')
      )
      ecsExecutionRole.addManagedPolicy(iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AmazonECSTaskExecutionRolePolicy'));

      const taskDefinition = new ecs.FargateTaskDefinition(this, 'llmGatewayTaskDefinition', {
        memoryLimitMiB: 2048,
        cpu: 1024,
        executionRole: ecsExecutionRole,
        taskRole: ecsExecutionRole,
        runtimePlatform: {
          cpuArchitecture: this.architecture == "x86" ? ecs.CpuArchitecture.X86_64 : ecs.CpuArchitecture.ARM64,
          operatingSystemFamily: ecs.OperatingSystemFamily.LINUX
        },
        
      });

      const container = taskDefinition.addContainer('llmGateway', {
        image: ecs.ContainerImage.fromEcrRepository(llmGatewayApiEcr, "latest"),
        logging: ecs.LogDrivers.awsLogs({ logGroup, streamPrefix: 'llmGatewayApi' }),
        environment: environment,
      });

      container.addPortMappings({
        containerPort: 80,
        hostPort: 80,
        protocol: ecs.Protocol.TCP
      });

      const service = new ecs.FargateService(this, 'LlmGatewayApiService', {
        serviceName: llmGatewayEcsTask,
        cluster,
        taskDefinition,
        desiredCount: 1,
        securityGroups: [llmGatewayAlbSecurityGroup],
        assignPublicIp: false,
        circuitBreaker: {
          enable:true,
          rollback:true
        },
        healthCheckGracePeriod: cdk.Duration.seconds(60),

      });

      //Create a target group for the ECS task
      targetGroupLlmGateway = this.createEcsTargetGroup(vpc, service, this.llmGatewayIsPublic ? "Public" : "Private")

      new cdk.CfnOutput(this, 'LlmgatewayEcsTask', {
        value: llmGatewayEcsTask,
        description: 'Name of the llmgateway ecs task'
      });
    }

    const api = new apigw.RestApi(this, "LlmGatewayApiGateway", {
      defaultCorsPreflightOptions: {
        allowOrigins: apigw.Cors.ALL_ORIGINS,
        allowMethods: apigw.Cors.ALL_METHODS,  // Make sure POST is included
        allowHeaders: ['Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Amz-User-Agent'],
        allowCredentials: true,
      },
    });

    const authHandlerRole = new iam.Role(this, "AuthHandlerRole", {
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
              effect: iam.Effect.ALLOW,
              actions: [
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret"
              ],
              resources: [saltSecret.secretArn]  // Restrict policy to this specific secret
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
              resources: [apiKeyTable.tableArn, `${apiKeyTable.tableArn}/index/${this.apiKeyValueHashIndex}`],
            })
          ],
        }),
      },
    })

    const nonAdminEndpoints = []

    const authHandler = new lambdaPython.PythonFunction(this, 'AuthHandlerFunction', {
      entry: path.join(__dirname, "../../lambdas/authorizer"),
      index: 'app.py',
      handler: 'handler',
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: this.architecture == "x86" ? lambda.Architecture.X86_64 : lambda.Architecture.ARM_64,
      environment: {
            USER_POOL_ID: this.userPool.userPoolId,
            APP_CLIENT_ID: this.applicationLoadBalanceruserPoolClient.userPoolClientId,
            ADMIN_LIST: this.adminList,
            COGNITO_DOMAIN_PREFIX: this.cognitoDomainPrefix,
            REGION: this.regionValue,
            NON_ADMIN_ENDPOINTS: this.nonAdminEndpoints,
            API_KEY_EXCLUDED_ENDPOINTS: this.apiKeyExcludedEndpoints,
            SALT_SECRET: saltSecret.secretName,
            API_KEY_TABLE_NAME: apiKeyTable.tableName
          },
      role: authHandlerRole
    });

    const authorizer = new apigw.TokenAuthorizer(this,
      "Authorizer",
      {
        handler: authHandler,
        identitySource: "method.request.header.Authorization",
      },
    )

    this.createApiKeyHandlerApi(api, authorizer, apiKeyTable, saltSecret, vpcParams, apiKeyEcr)
    this.createQuotaHandlerApi(api, authorizer, apiKeyTable, saltSecret, quotaTable, vpcParams, quotaEcr, defaultQuotaParameter)
    this.createModelAccessHandlerApi(api, authorizer, apiKeyTable, saltSecret, modelAccessTable, vpcParams, modelAccessEcr, defaultModelAccessParameter)

    let llmGatewayAlb : elbv2.ApplicationLoadBalancer;
    if (this.llmGatewayIsPublic) {
      llmGatewayAlb = new elbv2.ApplicationLoadBalancer(this, 'PublicLlmGatewayAlb', {
        vpc,
        internetFacing: true, // Not internet-facing
        securityGroup: llmGatewayAlbSecurityGroup,
        loadBalancerName: 'PublicLlmGatewayAlb',
      });
    }
    else {
      llmGatewayAlb = new elbv2.ApplicationLoadBalancer(this, 'PrivateLlmGatewayAlb', {
        vpc,
        internetFacing: false, // Not internet-facing
        securityGroup: llmGatewayAlbSecurityGroup,
        loadBalancerName: 'PrivateLlmGatewayAlb',
      });
    }

    const llmGatewayAppListener = llmGatewayAlb.addListener('LlmGatewayAppListener', {
      port: 443,
      protocol: elbv2.ApplicationProtocol.HTTPS,
      certificates: [
        { certificateArn: this.llmGatewayCertArn },
        { certificateArn: this.uiCertArn }
      ],
      defaultAction: elbv2.ListenerAction.fixedResponse(200, {
        contentType: "text/plain",
        messageBody: "This is the default action."
      }),
    });

    llmGatewayAppListener.addAction('ForwardToLambdaAction', {
      priority: 10,
      conditions: [elbv2.ListenerCondition.hostHeaders([this.llmGatewayDomainName])],
      action: elbv2.ListenerAction.forward([targetGroupLlmGateway])
    });

    const llmGatewayAppListener80 = llmGatewayAlb.addListener('LlmGatewayAppListener80', {
      port: 80,
      protocol: elbv2.ApplicationProtocol.HTTP,
      defaultAction: elbv2.ListenerAction.redirect({
        port:"443",
        protocol: "HTTPS",
        permanent: true
      })
    });

    const domainParts = this.llmGatewayDomainName.split(".");
    const domainName = domainParts.slice(1).join(".");
    const hostName = domainParts[0];

    // Retrieve the existing Route 53 hosted zone
    const hostedZone = route53.HostedZone.fromLookup(this, 'ZoneAlb', {
      domainName: `${domainName}.`
    });

    // Create Route 53 A record pointing to the ALB
    new route53.ARecord(this, 'AliasRecordAlb', {
      zone: hostedZone,
      recordName: hostName,
      target: route53.RecordTarget.fromAlias({
        bind: () => ({
          dnsName: llmGatewayAlb.loadBalancerDnsName,
          hostedZoneId: llmGatewayAlb.loadBalancerCanonicalHostedZoneId,
          evaluateTargetHealth: true,
        })
      })
    });

    const LlmGatewayUrl = "https://" + this.llmGatewayDomainName + "/api/v1"
    new cdk.CfnOutput(this, 'LlmGatewayUrl', {
      value: LlmGatewayUrl,
      description: 'The url of the llmgateway private application load balancer'
    });

    //Replace api.apiEndpoint with the url of the application load balancer
    this.setUpStreamlit(llmGatewayAlb, llmGatewayAppListener, llmGatewayAlbSecurityGroup, cluster, vpc, LlmGatewayUrl, api)
  }

  createSaltSecret() : secretsmanager.Secret {
    return new secretsmanager.Secret(this, 'MySaltSecret', {
      generateSecretString: {
        secretStringTemplate: JSON.stringify({ salt: this.salt }),
        generateStringKey: 'dummyKey'  // Required by AWS but not used since we provide the complete template
      }
    });
  }

  createModelAccessHandlerApi(api: apigw.RestApi, authorizer: apigw.TokenAuthorizer, apiKeyTable: dynamodb.ITable, saltSecret: secretsmanager.ISecret, modelAccessTable: dynamodb.ITable, vpcParams: object, modelAccessEcr: ecr.IRepository, defaultModelAccessParameter:ssm.StringParameter){
    const modelAccessHandler = new lambda.DockerImageFunction(this, 'modelAccessHandler', {
      functionName: this.modelAccessHandlerFunctionName,
      code: lambda.DockerImageCode.fromEcr(modelAccessEcr, { tag: "latest" }),
      role: this.createModelAccessLambdaRole("modelAccessHandlerRole", modelAccessTable, defaultModelAccessParameter, apiKeyTable, this.apiKeyValueHashIndex, saltSecret),
      architecture: this.architecture == "x86" ? lambda.Architecture.X86_64 : lambda.Architecture.ARM_64,
      environment: {
        REGION: this.regionValue,
        MODEL_ACCESS_TABLE_NAME: modelAccessTable.tableName,
        DEFAULT_MODEL_ACCESS_PARAMETER_NAME: defaultModelAccessParameter.parameterName,
        COGNITO_DOMAIN_PREFIX: this.cognitoDomainPrefix,
        NON_ADMIN_ENDPOINTS: this.nonAdminEndpoints,
        API_KEY_EXCLUDED_ENDPOINTS: this.apiKeyExcludedEndpoints,
        USER_POOL_ID: this.userPool.userPoolId,
        APP_CLIENT_ID: this.applicationLoadBalanceruserPoolClient.userPoolClientId,
        ADMIN_LIST: this.adminList,
        SALT_SECRET: saltSecret.secretName,
        API_KEY_TABLE_NAME: apiKeyTable.tableName
      },
      timeout: cdk.Duration.minutes(15),
      memorySize: 512,
      ...vpcParams,
    });

    const modelAccessResource = api.root.addResource('modelaccess');

    // Add GET endpoint
    modelAccessResource.addMethod('GET', new apigw.LambdaIntegration(modelAccessHandler), {
      authorizer: authorizer
    });

    // Add a new resource for the currentuser under modelaccess
    const currentuserResource = modelAccessResource.addResource('currentuser');

    // Add GET method for the /modelaccess/currentusersummary endpoint
    currentuserResource.addMethod('GET', new apigw.LambdaIntegration(modelAccessHandler), {
      authorizer: authorizer
    });

    // Add POST endpoint
    modelAccessResource.addMethod('POST', new apigw.LambdaIntegration(modelAccessHandler), {
      authorizer: authorizer
    });

    // Add DELETE endpoint
    modelAccessResource.addMethod('DELETE', new apigw.LambdaIntegration(modelAccessHandler), {
      authorizer: authorizer
    });

    new cdk.CfnOutput(this, 'ModelAccessLambdaFunctionName', {
      value: modelAccessHandler.functionName,
      description: 'Name of the model access lambda function'
    });

    return api
  }

  createQuotaHandlerApi(api: apigw.RestApi, authorizer: apigw.TokenAuthorizer, apiKeyTable: dynamodb.ITable, saltSecret: secretsmanager.ISecret, quotaTable: dynamodb.ITable, vpcParams: object, quotaHandlerEcr: ecr.IRepository, defaultQuotaParameter:ssm.StringParameter) {

    const quotaHandler = new lambda.DockerImageFunction(this, 'quotaHandler', {
      functionName: this.quotaHandlerFunctionName,
      code: lambda.DockerImageCode.fromEcr(quotaHandlerEcr, { tag: "latest" }),
      role: this.createQuotaLambdaRole("quotaHandlerRole", quotaTable, defaultQuotaParameter, apiKeyTable, this.apiKeyValueHashIndex, saltSecret),
      architecture: this.architecture == "x86" ? lambda.Architecture.X86_64 : lambda.Architecture.ARM_64,
      environment: {
        REGION: this.regionValue,
        QUOTA_TABLE_NAME: quotaTable.tableName,
        DEFAULT_QUOTA_PARAMETER_NAME: defaultQuotaParameter.parameterName,
        COGNITO_DOMAIN_PREFIX: this.cognitoDomainPrefix,
        NON_ADMIN_ENDPOINTS: this.nonAdminEndpoints,
        API_KEY_EXCLUDED_ENDPOINTS: this.apiKeyExcludedEndpoints,
        USER_POOL_ID: this.userPool.userPoolId,
        APP_CLIENT_ID: this.applicationLoadBalanceruserPoolClient.userPoolClientId,
        ADMIN_LIST: this.adminList,
        SALT_SECRET: saltSecret.secretName,
        API_KEY_TABLE_NAME: apiKeyTable.tableName
      },
      timeout: cdk.Duration.minutes(15),
      memorySize: 512,
      ...vpcParams,
    });

    const quotaResource = api.root.addResource('quota');

    // Add GET endpoint
    quotaResource.addMethod('GET', new apigw.LambdaIntegration(quotaHandler), {
      authorizer: authorizer
    });

    // Add a new resource for the summary under quota
    const summaryResource = quotaResource.addResource('summary');

    // Add a new resource for the summary under quota
    const currentusersummaryResource = quotaResource.addResource('currentusersummary');

    // Add GET method for the /quota/summary endpoint
    summaryResource.addMethod('GET', new apigw.LambdaIntegration(quotaHandler), {
        authorizer: authorizer
    });

    // Add GET method for the /quota/currentusersummary endpoint
    currentusersummaryResource.addMethod('GET', new apigw.LambdaIntegration(quotaHandler), {
      authorizer: authorizer
    });

    // Add POST endpoint
    quotaResource.addMethod('POST', new apigw.LambdaIntegration(quotaHandler), {
      authorizer: authorizer
    });

    // Add DELETE endpoint
    quotaResource.addMethod('DELETE', new apigw.LambdaIntegration(quotaHandler), {
      authorizer: authorizer
    });

    new cdk.CfnOutput(this, 'QuotaLambdaFunctionName', {
      value: quotaHandler.functionName,
      description: 'Name of the quota lambda function'
    });

    return api

  }

  createApiKeyHandlerApi(api: apigw.RestApi, authorizer: apigw.TokenAuthorizer, apiKeyTable: dynamodb.ITable, saltSecret: secretsmanager.ISecret, vpcParams: object, apiKeyEcr: ecr.IRepository) : apigw.RestApi {
    const apiKeyHandler = new lambda.DockerImageFunction(this, 'apiKeyHandler', {
      functionName: this.apiKeyHandlerFunctionName,
      code: lambda.DockerImageCode.fromEcr(apiKeyEcr, { tag: "latest" }),
      role: this.createApiKeyLambdaRole("apiKeyHandlerRole", apiKeyTable, this.apiKeyValueHashIndex, saltSecret),
      architecture: this.architecture == "x86" ? lambda.Architecture.X86_64 : lambda.Architecture.ARM_64,
      environment: {
        API_KEY_TABLE_NAME: apiKeyTable.tableName,
        COGNITO_DOMAIN_PREFIX: this.cognitoDomainPrefix,
        REGION: this.regionValue,
        SALT_SECRET: saltSecret.secretName,
        NON_ADMIN_ENDPOINTS: this.nonAdminEndpoints,
        API_KEY_EXCLUDED_ENDPOINTS: this.apiKeyExcludedEndpoints,
        USER_POOL_ID: this.userPool.userPoolId,
        APP_CLIENT_ID: this.applicationLoadBalanceruserPoolClient.userPoolClientId,
        ADMIN_LIST: this.adminList,
      },
      timeout: cdk.Duration.minutes(15),
      memorySize: 512,
      ...vpcParams,
    });

    const apiKeyResource = api.root.addResource('apikey');

    // Add GET endpoint
    apiKeyResource.addMethod('GET', new apigw.LambdaIntegration(apiKeyHandler), {
      authorizer: authorizer
    });

    // Add POST endpoint
    apiKeyResource.addMethod('POST', new apigw.LambdaIntegration(apiKeyHandler), {
      authorizer: authorizer
    });

    // Add DELETE endpoint
    apiKeyResource.addMethod('DELETE', new apigw.LambdaIntegration(apiKeyHandler), {
      authorizer: authorizer
    });

    new cdk.CfnOutput(this, 'ApiKeyLambdaFunctionName', {
      value: this.apiKeyHandlerFunctionName,
      description: 'Name of the api key lambda function'
    });

    return api
  }

  setUpCognito() {
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

  setUpStreamlit(lb: elbv2.ApplicationLoadBalancer, appListener:elbv2.ApplicationListener, albSecurityGroup: ec2.SecurityGroup, cluster: ecs.Cluster, vpc: ec2.Vpc, llmGatewayUrl: string, apiGatewayApi: apigw.RestApi) {
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
        LlmGatewayUrl: llmGatewayUrl,
        ApiGatewayURL: apiGatewayApi.url,
        AdminList: this.adminList,
        Region: this.regionValue,
        CognitoDomainPrefix: this.cognitoDomainPrefix,
        CognitoClientId: this.applicationLoadBalanceruserPoolClient.userPoolClientId
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

    const appSecurityGroup = new ec2.SecurityGroup(this, 'AppSecurityGroup', {
      securityGroupName: 'LlmGatewayUI-sg',
      vpc,
      allowAllOutbound: true,
    });

    appSecurityGroup.addIngressRule(albSecurityGroup, ec2.Port.tcp(8501));

    const llmGatewayUIEcsTask = "LlmGatewayUI"
    const service = new ecs.FargateService(this, 'Service', {
      serviceName: llmGatewayUIEcsTask,
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

    new cdk.CfnOutput(this, 'LlmgatewayUIEcsTask', {
      value: llmGatewayUIEcsTask,
      description: 'Name of the llmgateway ecs task'
    });

    const targetGroup = new elbv2.ApplicationTargetGroup(this, 'AppTG', {
      vpc,
      targetGroupName: 'LlmGatewayUI',
      protocol: elbv2.ApplicationProtocol.HTTP,
      targetType: elbv2.TargetType.IP,
      port: 8501,
      targets: [service]
    });

    appListener.addAction("authenticate-cognito", {
      priority: 20,
      conditions: [elbv2.ListenerCondition.hostHeaders([this.uiDomainName])],
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

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Create API Gateway resources.

    // const modelPolicyStore = this.createSecureDdbTable(
    //   this.stackPrefix + "ModelPolicyStore",
    //   "id"
    // );
    //const modelEngineName = this.stackPrefix + "ModelEngine";
    //const modelEngine = this.createSecureDdbTable(modelEngineName, "id");

    // Create a chat history database.
    const chatHistoryTable = this.createSecureDdbTable(
      this.chatHistoryTableName,
      "id"
    );

    // Create a table for storing costs of using different LLMs.
    //const costTable = this.createSecureDdbTable("CostTable", "id");
    //const costLambda = this.createTokenCountLambda("CostLambda", costTable);
    const apiKeyEcrRepo = ecr.Repository.fromRepositoryName(
      this,
      this.apiKeyEcrRepoName!,
      this.apiKeyEcrRepoName!
    );

    const llmGatewayEcrRepo = ecr.Repository.fromRepositoryName(
      this,
      this.llmGatewayRepoName!,
      this.llmGatewayRepoName!
    );

    const quotaEcrRepo = ecr.Repository.fromRepositoryName(
      this,
      this.quotaRepoName!,
      this.quotaRepoName!
    );

    const modelAccessEcrRepo = ecr.Repository.fromRepositoryName(
      this,
      this.modelAccessRepoName!,
      this.modelAccessRepoName!
    );

    this.createAlbApi(chatHistoryTable, apiKeyEcrRepo, llmGatewayEcrRepo, quotaEcrRepo, modelAccessEcrRepo)
  }
}
