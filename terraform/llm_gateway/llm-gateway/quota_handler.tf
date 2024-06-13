resource "aws_security_group" "llm_gateway_rest_model_access_lambda_function_security_group" {
  name        = "${local.name}-quota-authorizer-security-group"
  vpc_id      = local.vpc_id
  description = "Security Group for quota handler"
  egress {
    description = "Allow https traffic"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}


module "llm_gateway_rest_quota_handler" {

  source  = "terraform-aws-modules/lambda/aws"
  version = "7.5.0"

  create_layer   = false
  create_package = false

  function_name = join("", [local.name, "-quota-handler"])
  architectures = [local.architectures]

  vpc_subnet_ids                     = local.private_subnet_ids
  vpc_security_group_ids             = [aws_security_group.llm_gateway_rest_model_access_lambda_function_security_group.id]
  attach_network_policy              = true
  replace_security_groups_on_destroy = true
  replacement_security_group_ids = [local.vpc_default_security_group_id]

  environment_variables = {
    REGION : local.region,
    QUOTA_TABLE_NAME : aws_dynamodb_table.llm_gateway_rest_quota.name,
    DEFAULT_QUOTA_PARAMETER_NAME : aws_ssm_parameter.llm_gateway_rest_ssm_parameter_default_quota.name
    COGNITO_DOMAIN_PREFIX : local.cognito_domain_prefix
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
        aws_dynamodb_table.llm_gateway_rest_quota.arn,
      ],
    }

    ssm = {
      effect = "Allow",
      actions = [
        "ssm:GetParameter"
      ],
      resources = [aws_ssm_parameter.llm_gateway_rest_ssm_parameter_default_quota.arn]
    }

    secrets_manager = {
      effect = "Allow",
      actions = [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      resources = [aws_secretsmanager_secret.llm_gateway_rest_secret_salt.arn]
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

  }
  package_type               = "Image"
  image_uri                  = "${data.aws_ecr_repository.quotaEcrRepo.repository_url}:latest"
  cloudwatch_logs_kms_key_id = local.kms_key_arn
  tags                       = local.tags
}


resource "aws_api_gateway_resource" "llm_gateway_rest_quota_resource" {
  parent_id   = aws_api_gateway_rest_api.llm_gateway_rest_api.root_resource_id
  path_part   = "quota"
  rest_api_id = aws_api_gateway_rest_api.llm_gateway_rest_api.id
}


resource "aws_api_gateway_resource" "llm_gateway_rest_quota_summary_resource" {
  parent_id   = aws_api_gateway_resource.llm_gateway_rest_quota_resource.id
  path_part   = "summary"
  rest_api_id = aws_api_gateway_rest_api.llm_gateway_rest_api.id
}

resource "aws_api_gateway_resource" "llm_gateway_rest_quota_current_user_summary_resource" {
  parent_id   = aws_api_gateway_resource.llm_gateway_rest_quota_resource.id
  path_part   = "currentusersummary"
  rest_api_id = aws_api_gateway_rest_api.llm_gateway_rest_api.id
}

resource "aws_api_gateway_method" "llm_gateway_rest_quota_method_get" {
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.llm_gateway_rest_authorizer.id
  http_method   = "GET"
  resource_id   = aws_api_gateway_resource.llm_gateway_rest_quota_resource.id
  rest_api_id   = aws_api_gateway_rest_api.llm_gateway_rest_api.id
}

resource "aws_api_gateway_method" "llm_gateway_rest_quota_method_post" {
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.llm_gateway_rest_authorizer.id
  http_method   = "POST"
  resource_id   = aws_api_gateway_resource.llm_gateway_rest_quota_resource.id
  rest_api_id   = aws_api_gateway_rest_api.llm_gateway_rest_api.id
}

resource "aws_api_gateway_method" "llm_gateway_rest_quota_method_delete" {
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.llm_gateway_rest_authorizer.id
  http_method   = "DELETE"
  resource_id   = aws_api_gateway_resource.llm_gateway_rest_quota_resource.id
  rest_api_id   = aws_api_gateway_rest_api.llm_gateway_rest_api.id
}

resource "aws_api_gateway_method" "llm_gateway_rest_quota_method_summary" {
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.llm_gateway_rest_authorizer.id
  http_method   = "GET"
  resource_id   = aws_api_gateway_resource.llm_gateway_rest_quota_summary_resource.id
  rest_api_id   = aws_api_gateway_rest_api.llm_gateway_rest_api.id
}

resource "aws_api_gateway_method" "llm_gateway_rest_quota_method_current_user_summary" {
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.llm_gateway_rest_authorizer.id
  http_method   = "GET"
  resource_id   = aws_api_gateway_resource.llm_gateway_rest_quota_current_user_summary_resource.id
  rest_api_id   = aws_api_gateway_rest_api.llm_gateway_rest_api.id
}

resource "aws_api_gateway_integration" "llm_gateway_rest_quota_method_get_integration" {
  http_method             = aws_api_gateway_method.llm_gateway_rest_quota_method_get.http_method
  resource_id             = aws_api_gateway_resource.llm_gateway_rest_quota_resource.id
  rest_api_id             = aws_api_gateway_rest_api.llm_gateway_rest_api.id
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = module.llm_gateway_rest_quota_handler.lambda_function_invoke_arn
}

resource "aws_api_gateway_integration" "llm_gateway_rest_quota_method_post_integration" {
  http_method             = aws_api_gateway_method.llm_gateway_rest_quota_method_post.http_method
  resource_id             = aws_api_gateway_resource.llm_gateway_rest_quota_resource.id
  rest_api_id             = aws_api_gateway_rest_api.llm_gateway_rest_api.id
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = module.llm_gateway_rest_quota_handler.lambda_function_invoke_arn
}

resource "aws_api_gateway_integration" "llm_gateway_rest_quota_method_delete_integration" {
  http_method             = aws_api_gateway_method.llm_gateway_rest_quota_method_delete.http_method
  resource_id             = aws_api_gateway_resource.llm_gateway_rest_quota_resource.id
  rest_api_id             = aws_api_gateway_rest_api.llm_gateway_rest_api.id
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = module.llm_gateway_rest_quota_handler.lambda_function_invoke_arn
}

resource "aws_api_gateway_integration" "llm_gateway_rest_quota_summary_method_get_integration" {
  http_method             = aws_api_gateway_method.llm_gateway_rest_quota_method_summary.http_method
  resource_id             = aws_api_gateway_resource.llm_gateway_rest_quota_summary_resource.id
  rest_api_id             = aws_api_gateway_rest_api.llm_gateway_rest_api.id
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = module.llm_gateway_rest_quota_handler.lambda_function_invoke_arn
}

resource "aws_api_gateway_integration" "llm_gateway_rest_quota_current_user_summary_method_get_integration" {
  http_method             = aws_api_gateway_method.llm_gateway_rest_quota_method_current_user_summary.http_method
  resource_id             = aws_api_gateway_resource.llm_gateway_rest_quota_current_user_summary_resource.id
  rest_api_id             = aws_api_gateway_rest_api.llm_gateway_rest_api.id
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = module.llm_gateway_rest_quota_handler.lambda_function_invoke_arn
}
