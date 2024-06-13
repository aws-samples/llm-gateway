resource "aws_security_group" "llm_gateway_rest_authorizer_lambda_function_security_group" {
  name        = "${local.name}-authorizer-security-group"
  vpc_id      = local.vpc_id
  description = "Security Group for authorizer lambda function"

  egress {
    description = "Allow https traffic"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

module "llm_gateway_rest_authorizer_function" {

  source  = "terraform-aws-modules/lambda/aws"
  version = "7.5.0"


  handler       = "app.handler"
  runtime       = "python3.12"
  create_layer  = false
  function_name = join("", [local.name, "-authorizer"])
  architectures = [local.architectures]

  vpc_subnet_ids                     = local.private_subnet_ids
  vpc_security_group_ids             = [aws_security_group.llm_gateway_rest_authorizer_lambda_function_security_group.id]
  attach_network_policy              = true
  replace_security_groups_on_destroy = true
  replacement_security_group_ids = [local.vpc_default_security_group_id]


  environment_variables = {
    USER_POOL_ID : local.user_pool_id
    APP_CLIENT_ID : local.app_client_id
    ADMIN_ONLY : "true",
    ADMIN_LIST : local.admin_list,
    COGNITO_DOMAIN_PREFIX : local.cognito_domain_prefix,
    REGION : local.region
    NON_ADMIN_ENDPOINTS : "apikey,quota/currentusersummary,modelaccess/currentuser",
    API_KEY_EXCLUDED_ENDPOINTS : "apikey",
    SALT_SECRET : aws_secretsmanager_secret.llm_gateway_rest_secret_salt.name
    API_KEY_TABLE_NAME : aws_dynamodb_table.llm_gateway_rest_apikey.name
  }

  publish = true
  timeout = 900

  allowed_triggers = {
    "APIGatewayAny" = {
      service    = "apigateway"
      source_arn = "${aws_api_gateway_rest_api.llm_gateway_rest_api.execution_arn}/*/*"
    }
  }

  attach_policy_statements = true
  policy_statements = {

    kms_decrypt = {
      effect = "Allow",
      actions = [
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:ReEncrypt*",
        "kms:GenerateDataKey*",
        "kms:DescribeKey"
      ],
      "resources" : [local.kms_key_arn],
    }

    cloudwatch = {
      effect = "Allow",
      actions = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
      ],
      "resources" : ["*"],
    }

    dynamodb = {
      effect = "Allow",
      actions = [
        "dynamodb:BatchWriteItem",
        "dynamodb:DeleteItem",
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:UpdateItem"
      ],
      "resources" : [
        aws_dynamodb_table.llm_gateway_rest_apikey.arn,
        "${aws_dynamodb_table.llm_gateway_rest_apikey.arn}/index/*"
      ],
    }
    secrets_manager = {
      effect = "Allow",
      actions = [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      resources = [aws_secretsmanager_secret.llm_gateway_rest_secret_salt.arn]
    }
  }

  source_path                = "${path.module}/../../../lambdas/authorizer/"
  cloudwatch_logs_kms_key_id = local.kms_key_arn
  tags                       = local.tags
}

# Create Cognito User pool Authorizer
resource "aws_api_gateway_authorizer" "llm_gateway_rest_authorizer" {

  identity_source                  = "method.request.header.Authorization"
  name                             = "${local.name}-apikey-Authorizer"
  type                             = "TOKEN"
  authorizer_result_ttl_in_seconds = local.authorizer_result_ttl_in_seconds
  authorizer_uri                   = module.llm_gateway_rest_authorizer_function.lambda_function_invoke_arn
  rest_api_id                      = aws_api_gateway_rest_api.llm_gateway_rest_api.id

}