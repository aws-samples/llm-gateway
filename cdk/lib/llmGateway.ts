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
import * as lambdaNode from "aws-cdk-lib/aws-lambda-nodejs"
import * as elbv2 from "aws-cdk-lib/aws-elasticloadbalancingv2"
import * as elbv2Actions from "aws-cdk-lib/aws-elasticloadbalancingv2-actions";
import * as route53 from "aws-cdk-lib/aws-route53";
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as targets from 'aws-cdk-lib/aws-elasticloadbalancingv2-targets';
import * as ssm from "aws-cdk-lib/aws-ssm";
import * as lambdaPython from '@aws-cdk/aws-lambda-python-alpha'
import * as acm from 'aws-cdk-lib/aws-certificatemanager';
import * as kms from 'aws-cdk-lib/aws-kms';

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
  enabledModels = this.node.tryGetContext("enabledModels");
  benchmarkMode = String(this.node.tryGetContext("llmGatewayIsPublic")).toLowerCase() == "true";
  benchmarkRepoName = this.node.tryGetContext("benchmarkRepoName");

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

  createSecureDdbTable(tableName: string, partitionKeyName: string, kmsKey: kms.Key) {
    const table = new dynamodb.Table(this, tableName, {
      partitionKey: {
        name: partitionKeyName,
        type: dynamodb.AttributeType.STRING,
      },
      encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: kmsKey,
      pointInTimeRecovery: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      readCapacity: 100,
      writeCapacity:100
    });
    return table;
  }

  createSecureDdbTableWithSortKey(
    tableName: string,
    partitionKeyName: string,
    sortKeyName: string,
    secondaryIndexName: string | null,
    secondaryIndexPartitionKeyName: string | null,
    kmsKey: kms.Key
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
      encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: kmsKey,
      pointInTimeRecovery: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      readCapacity: 100,
      writeCapacity:100
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
        readCapacity: 400,
        writeCapacity:25
      });
    }

    return table;
  };

  createLlmGatewayRole(
    roleName: string,
    quotaTable: dynamodb.Table,
    modelAccessTable: dynamodb.Table,
    requestDetailsTable: dynamodb.Table,
    apiKeyTable: dynamodb.Table,
    apiKeyValueHashIndex: string,
    secret: secretsmanager.Secret,
    defaultQuotaParameter: ssm.StringParameter,
    defaultModelAccessParameter: ssm.StringParameter,
    assumedBy: iam.ServicePrincipal,
    kmsKey: kms.Key
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
              resources: [apiKeyTable.tableArn, `${apiKeyTable.tableArn}/index/${apiKeyValueHashIndex}`, quotaTable.tableArn, modelAccessTable.tableArn, requestDetailsTable.tableArn],
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
            }),
            new iam.PolicyStatement({
              sid: "KmsDecrypt",
              effect: iam.Effect.ALLOW,
              actions: [
                "kms:Encrypt",
                "kms:Decrypt",
                "kms:ReEncrypt*",
                "kms:GenerateDataKey*",
                "kms:DescribeKey"
              ],
              resources: [kmsKey.keyArn],
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
    secret: secretsmanager.ISecret,
    kmsKey: kms.Key
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
            new iam.PolicyStatement({
              sid: "KmsDecrypt",
              effect: iam.Effect.ALLOW,
              actions: [
                "kms:Encrypt",
                "kms:Decrypt",
                "kms:ReEncrypt*",
                "kms:GenerateDataKey*",
                "kms:DescribeKey"
              ],
              resources: [kmsKey.keyArn],
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
    secret: secretsmanager.ISecret,
    kmsKey: kms.Key
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
            }),
            new iam.PolicyStatement({
              sid: "KmsDecrypt",
              effect: iam.Effect.ALLOW,
              actions: [
                "kms:Encrypt",
                "kms:Decrypt",
                "kms:ReEncrypt*",
                "kms:GenerateDataKey*",
                "kms:DescribeKey"
              ],
              resources: [kmsKey.keyArn],
            }),
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
    secret: secretsmanager.ISecret,
    kmsKey: kms.Key
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
            }),
            new iam.PolicyStatement({
              sid: "KmsDecrypt",
              effect: iam.Effect.ALLOW,
              actions: [
                "kms:Encrypt",
                "kms:Decrypt",
                "kms:ReEncrypt*",
                "kms:GenerateDataKey*",
                "kms:DescribeKey"
              ],
              resources: [kmsKey.keyArn],
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
    apiKeyEcr: ecr.IRepository,
    llmGatewayApiEcr: ecr.IRepository,
    quotaEcr: ecr.IRepository,
    modelAccessEcr: ecr.IRepository,
    benchmarkEcr: ecr.IRepository
  ) {

    const kmsKey = new kms.Key(this, "llmGatewayKmsKey", {
      keyUsage: kms.KeyUsage.ENCRYPT_DECRYPT,
      description: "llmGatewayKmsKey",
      enabled: true,
      alias: "llmGatewayKmsKey",
      enableKeyRotation: true,
      policy: new iam.PolicyDocument({
        statements: [
          new iam.PolicyStatement({
            effect: iam.Effect.ALLOW,
            actions: ['kms:*'],  // Granting all KMS actions
            resources: ['*'],    // Applies to all resources
            principals: [new iam.ArnPrincipal(`arn:aws:iam::${cdk.Aws.ACCOUNT_ID}:root`)],
          }),
          new iam.PolicyStatement({
            sid: "KmsDecrypt",
            effect: iam.Effect.ALLOW,
            actions: [
              "kms:Encrypt*",
              "kms:Decrypt*",
              "kms:ReEncrypt*",
              "kms:GenerateDataKey*",
              "kms:Describe*"
            ],
            resources: ["*"],
            principals: [new iam.ServicePrincipal("logs.amazonaws.com")],
            conditions: {
              'ArnLike': {
                'kms:EncryptionContext:aws:logs:arn': `arn:aws:logs:${cdk.Aws.REGION}:${cdk.Aws.ACCOUNT_ID}:log-group:*`
              }
            }
          }),
        ],
      }),
    })


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
      kmsKey
    )

    const quotaTable = this.createSecureDdbTableWithSortKey(
      this.quotaTableName,
      this.quotaTablePartitionKey,
      this.quotaTableSortKey,
      null,
      null,
      kmsKey
    )

    const requestDetailsTable = this.createSecureDdbTableWithSortKey(
      this.requestDetailsTableName,
      this.requestDetailsTablePartitionKey,
      this.requestDetailsTableSortKey,
      null,
      null,
      kmsKey
    )

    const saltSecret = this.createSaltSecret(kmsKey)

    const apiKeyTable = this.createSecureDdbTableWithSortKey(
      this.apiKeyTableName,
      this.apiKeyTablePartitionKey,
      this.apiKeyTableSortKey,
      this.apiKeyValueHashIndex, 
      this.apiKeyTableIndexPartitionKey,
      kmsKey
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
    let targetGroupBenchmark :elbv2.ApplicationTargetGroup;
    const LlmGatewayUrl = "https://" + this.llmGatewayDomainName

    const environment = {
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
      DEBUG: this.debug,
      ENABLED_MODELS: this.enabledModels,
      BENCHMARK_MODE: String(this.benchmarkMode),
      LLM_GATEWAY_URL: LlmGatewayUrl
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
        quotaTable,
        modelAccessTable,
        requestDetailsTable,
        apiKeyTable,
        this.apiKeyValueHashIndex,
        saltSecret,
        defaultQuotaParameter,
        defaultModelAccessParameter,
        new iam.ServicePrincipal("lambda.amazonaws.com"),
        kmsKey
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
        removalPolicy: cdk.RemovalPolicy.DESTROY,
        encryptionKey: kmsKey
      });

      const ecsExecutionRole = this.createLlmGatewayRole(
        "llmGatewayEcsRole",
        quotaTable,
        modelAccessTable,
        requestDetailsTable,
        apiKeyTable,
        this.apiKeyValueHashIndex,
        saltSecret,
        defaultQuotaParameter,
        defaultModelAccessParameter,
        new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
        kmsKey
      )
      ecsExecutionRole.addManagedPolicy(iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AmazonECSTaskExecutionRolePolicy'));

      const taskDefinition = new ecs.FargateTaskDefinition(this, 'llmGatewayTaskDefinition', {
        memoryLimitMiB: 4096,
        cpu: 2048,
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
        desiredCount: 32,
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
        { certificateArn: this.llmGatewayCertArn }
      ],
      defaultAction: elbv2.ListenerAction.fixedResponse(200, {
        contentType: "text/plain",
        messageBody: "This is the default action."
      }),
    });

    const llmGatewayUiCert = acm.Certificate.fromCertificateArn(this, 'llmGatewayUiCert', this.uiCertArn);
    llmGatewayAppListener.addCertificates("llmGatewayUiCert", [llmGatewayUiCert])

    llmGatewayAppListener.addAction('ForwardToLlmGatewayEcsAction', {
      priority: 20,
      conditions: [elbv2.ListenerCondition.hostHeaders([this.llmGatewayDomainName]), elbv2.ListenerCondition.pathPatterns(['/api/v1*'])],
      action: elbv2.ListenerAction.forward([targetGroupLlmGateway])
    });

    if (this.benchmarkMode) {
      const logGroup = new logs.LogGroup(this, 'benchmarkLogGroup', {
        logGroupName: '/ecs/LlmGateway/benchmark',
        removalPolicy: cdk.RemovalPolicy.DESTROY,
        encryptionKey: kmsKey
      });
      const ecsBenchmarkExecutionRole = this.createLlmGatewayRole(
        "benchmarkEcsRole",
        quotaTable,
        modelAccessTable,
        requestDetailsTable,
        apiKeyTable,
        this.apiKeyValueHashIndex,
        saltSecret,
        defaultQuotaParameter,
        defaultModelAccessParameter,
        new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
        kmsKey
      )
      ecsBenchmarkExecutionRole.addManagedPolicy(iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AmazonECSTaskExecutionRolePolicy'));
      const benchmarkTaskDefinition = new ecs.FargateTaskDefinition(this, 'benchmarkTaskDefinition', {
        memoryLimitMiB: 2048,
        cpu: 1024,
        executionRole: ecsBenchmarkExecutionRole,
        taskRole: ecsBenchmarkExecutionRole,
        runtimePlatform: {
          cpuArchitecture: this.architecture == "x86" ? ecs.CpuArchitecture.X86_64 : ecs.CpuArchitecture.ARM64,
          operatingSystemFamily: ecs.OperatingSystemFamily.LINUX
        },
      });

      const benchmarkContainer = benchmarkTaskDefinition.addContainer('benchmark', {
        image: ecs.ContainerImage.fromEcrRepository(benchmarkEcr, "latest"),
        logging: ecs.LogDrivers.awsLogs({ logGroup, streamPrefix: 'benchmark' }),
        environment: environment,
      });

      benchmarkContainer.addPortMappings({
        containerPort: 8080,
        hostPort: 8080,
        protocol: ecs.Protocol.TCP
      });

      const benchmarkTask = "benchmark"
      const benchmarkService = new ecs.FargateService(this, 'BenchmarkApiService', {
        serviceName: benchmarkTask,
        cluster,
        taskDefinition:benchmarkTaskDefinition,
        desiredCount: 1,
        securityGroups: [llmGatewayAlbSecurityGroup],
        assignPublicIp: false,
        circuitBreaker: {
          enable:true,
          rollback:true
        },
        healthCheckGracePeriod: cdk.Duration.seconds(60),
      });

      const type = this.llmGatewayIsPublic ? "Public" : "Private"
      targetGroupBenchmark = new elbv2.ApplicationTargetGroup(this, 'benchmarkEcsTargetGroup' + type, {
        vpc,
        targetGroupName: 'benchmarkEcsTargetGroup' + type,
        protocol: elbv2.ApplicationProtocol.HTTP,
        targetType: elbv2.TargetType.IP,
        port: 80,
        targets: [benchmarkService],
        healthCheck: {
          enabled: true,
          path: "/benchmark/health"
        }
      });

      //Create a target group for the ECS task
      llmGatewayAppListener.addAction('ForwardToBenchmarkAction', {
        priority: 60,
        conditions: [elbv2.ListenerCondition.hostHeaders([this.llmGatewayDomainName]), elbv2.ListenerCondition.pathPatterns(['/benchmark*'])],
        action: elbv2.ListenerAction.forward([targetGroupBenchmark])
      });

      new cdk.CfnOutput(this, 'BenchmarkEcsTask', {
        value: benchmarkTask,
        description: 'Name of the benchmark ecs task'
      });
    }

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

    new cdk.CfnOutput(this, 'LlmGatewayUrl', {
      value: LlmGatewayUrl,
      description: 'The url of the llmgateway private application load balancer'
    });

    this.createApiKeyHandlerApi(llmGatewayAlb, llmGatewayAppListener, apiKeyTable, saltSecret, vpcParams, apiKeyEcr, kmsKey)
    this.createQuotaHandlerApi(llmGatewayAlb, llmGatewayAppListener, apiKeyTable, saltSecret, quotaTable, vpcParams, quotaEcr, defaultQuotaParameter, kmsKey)
    this.createModelAccessHandlerApi(llmGatewayAlb, llmGatewayAppListener, apiKeyTable, saltSecret, modelAccessTable, vpcParams, modelAccessEcr, defaultModelAccessParameter, kmsKey)


    this.setUpStreamlit(llmGatewayAlb, llmGatewayAppListener, llmGatewayAlbSecurityGroup, cluster, vpc, LlmGatewayUrl, kmsKey)
  }

  createSaltSecret(kmsKey: kms.Key) : secretsmanager.Secret {
    return new secretsmanager.Secret(this, 'MySaltSecret', {
      generateSecretString: {
        secretStringTemplate: JSON.stringify({ salt: this.salt }),
        generateStringKey: 'dummyKey'  // Required by AWS but not used since we provide the complete template
      },
      encryptionKey: kmsKey
    });
  }

  createModelAccessHandlerApi(lb: elbv2.ApplicationLoadBalancer, appListener:elbv2.ApplicationListener, apiKeyTable: dynamodb.ITable, saltSecret: secretsmanager.ISecret, modelAccessTable: dynamodb.ITable, vpcParams: object, modelAccessEcr: ecr.IRepository, defaultModelAccessParameter:ssm.StringParameter, ksmKey: kms.Key) {
    const logGroup = new logs.LogGroup(this, 'ModelAccessHandlerLogGroup', {
      logGroupName: 'ModelAccessHandlerLogGroup',
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      encryptionKey: ksmKey
    });
    
    const modelAccessHandler = new lambda.DockerImageFunction(this, 'modelAccessHandler', {
      functionName: this.modelAccessHandlerFunctionName,
      code: lambda.DockerImageCode.fromEcr(modelAccessEcr, { tag: "latest" }),
      role: this.createModelAccessLambdaRole("modelAccessHandlerRole", modelAccessTable, defaultModelAccessParameter, apiKeyTable, this.apiKeyValueHashIndex, saltSecret, ksmKey),
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
      logGroup: logGroup
    });

    const lambdaTarget = new targets.LambdaTarget(modelAccessHandler)

    const targetGroup = new elbv2.ApplicationTargetGroup(this, 'LlmGatewayModelAccessLambda', {
      targetGroupName: 'LlmGatewayModelAccessLambda',
      targetType: elbv2.TargetType.LAMBDA,
      targets: [lambdaTarget]
    });

    appListener.addAction('ForwardToModelAccessLambdaAction', {
      priority: 30,
      conditions: [elbv2.ListenerCondition.hostHeaders([this.llmGatewayDomainName]), elbv2.ListenerCondition.pathPatterns(['/modelaccess*'])],
      action: elbv2.ListenerAction.forward([targetGroup])
    });

    new cdk.CfnOutput(this, 'ModelAccessLambdaFunctionName', {
      value: modelAccessHandler.functionName,
      description: 'Name of the model access lambda function'
    });
  }

  createQuotaHandlerApi(lb: elbv2.ApplicationLoadBalancer, appListener:elbv2.ApplicationListener, apiKeyTable: dynamodb.ITable, saltSecret: secretsmanager.ISecret, quotaTable: dynamodb.ITable, vpcParams: object, quotaHandlerEcr: ecr.IRepository, defaultQuotaParameter:ssm.StringParameter, ksmKey: kms.Key) {
    const logGroup = new logs.LogGroup(this, 'QuotaHandlerLogGroup', {
      logGroupName: 'QuotaHandlerLogGroup',
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      encryptionKey: ksmKey
    });

    const quotaHandler = new lambda.DockerImageFunction(this, 'quotaHandler', {
      functionName: this.quotaHandlerFunctionName,
      code: lambda.DockerImageCode.fromEcr(quotaHandlerEcr, { tag: "latest" }),
      role: this.createQuotaLambdaRole("quotaHandlerRole", quotaTable, defaultQuotaParameter, apiKeyTable, this.apiKeyValueHashIndex, saltSecret, ksmKey),
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
      logGroup: logGroup
    });

    const lambdaTarget = new targets.LambdaTarget(quotaHandler)

    const targetGroup = new elbv2.ApplicationTargetGroup(this, 'LlmGatewayQuotaLambda', {
      targetGroupName: 'LlmGatewayQuotaLambda',
      targetType: elbv2.TargetType.LAMBDA,
      targets: [lambdaTarget]
    });

    appListener.addAction('ForwardToQuotaLambdaAction', {
      priority: 40,
      conditions: [elbv2.ListenerCondition.hostHeaders([this.llmGatewayDomainName]), elbv2.ListenerCondition.pathPatterns(['/quota*'])],
      action: elbv2.ListenerAction.forward([targetGroup])
    });

    new cdk.CfnOutput(this, 'QuotaLambdaFunctionName', {
      value: quotaHandler.functionName,
      description: 'Name of the quota lambda function'
    });
  }

  createApiKeyHandlerApi(lb: elbv2.ApplicationLoadBalancer, appListener:elbv2.ApplicationListener, apiKeyTable: dynamodb.ITable, saltSecret: secretsmanager.ISecret, vpcParams: object, apiKeyEcr: ecr.IRepository, ksmKey: kms.Key) {
    const logGroup = new logs.LogGroup(this, 'ApiKeyHandlerLogGroup', {
      logGroupName: 'ApiKeyHandlerLogGroup',
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      encryptionKey: ksmKey
    });
    
    const apiKeyHandler = new lambda.DockerImageFunction(this, 'apiKeyHandler', {
      functionName: this.apiKeyHandlerFunctionName,
      code: lambda.DockerImageCode.fromEcr(apiKeyEcr, { tag: "latest" }),
      role: this.createApiKeyLambdaRole("apiKeyHandlerRole", apiKeyTable, this.apiKeyValueHashIndex, saltSecret, ksmKey),
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
        BENCHMARK_MODE: String(this.benchmarkMode)
      },
      timeout: cdk.Duration.minutes(15),
      memorySize: 512,
      ...vpcParams,
      logGroup: logGroup
    });

    const lambdaTarget = new targets.LambdaTarget(apiKeyHandler)

    const targetGroup = new elbv2.ApplicationTargetGroup(this, 'LlmGatewayApiKeyLambda', {
      targetGroupName: 'LlmGatewayApiKeyLambda',
      targetType: elbv2.TargetType.LAMBDA,
      targets: [lambdaTarget]
    });

    appListener.addAction('ForwardToApiKeyLambdaAction', {
      priority: 50,
      conditions: [elbv2.ListenerCondition.hostHeaders([this.llmGatewayDomainName]), elbv2.ListenerCondition.pathPatterns(['/apikey*'])],
      action: elbv2.ListenerAction.forward([targetGroup])
    });

    new cdk.CfnOutput(this, 'ApiKeyLambdaFunctionName', {
      value: this.apiKeyHandlerFunctionName,
      description: 'Name of the api key lambda function'
    });
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
          authFlows: {
            userPassword: true,
            custom: true,
            userSrp: true
          },
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

  setUpStreamlit(lb: elbv2.ApplicationLoadBalancer, appListener:elbv2.ApplicationListener, albSecurityGroup: ec2.SecurityGroup, cluster: ecs.Cluster, vpc: ec2.Vpc, llmGatewayUrl: string, kmsKey: kms.Key) {
    const logGroup = new logs.LogGroup(this, 'AppLogGroup', {
      logGroupName: '/ecs/LlmGateway/StreamlitUI',
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      encryptionKey: kmsKey
    });

    const ecsExecutionRole = new iam.Role(this, 'EcsExecutionRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      roleName: 'LlmGatewayUIRole'
    });

    ecsExecutionRole.addManagedPolicy(iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AmazonECSTaskExecutionRolePolicy'));
    ecsExecutionRole.addToPolicy(new iam.PolicyStatement({
      sid: "KmsDecrypt",
      effect: iam.Effect.ALLOW,
      actions: [
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:ReEncrypt*",
        "kms:GenerateDataKey*",
        "kms:DescribeKey"
      ],
      resources: [kmsKey.keyArn],
    }))

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
        AdminList: this.adminList,
        Region: this.regionValue,
        CognitoDomainPrefix: this.cognitoDomainPrefix,
        CognitoClientId: this.applicationLoadBalanceruserPoolClient.userPoolClientId,
        ENABLED_MODELS: this.enabledModels
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

    const targetGroup = new elbv2.ApplicationTargetGroup(this, 'LlmGatewayUI', {
      vpc,
      targetGroupName: 'LlmGatewayUI',
      protocol: elbv2.ApplicationProtocol.HTTP,
      targetType: elbv2.TargetType.IP,
      port: 8501,
      targets: [service]
    });

    appListener.addAction("authenticate-cognito", {
      priority: 10,
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

    const benchmarkEcrRepo = ecr.Repository.fromRepositoryName(
      this,
      this.benchmarkRepoName!,
      this.benchmarkRepoName!
    );

    this.createAlbApi(apiKeyEcrRepo, llmGatewayEcrRepo, quotaEcrRepo, modelAccessEcrRepo, benchmarkEcrRepo)
  }
}
