resource "aws_security_group" "llm_gateway_rest_modelaccess_lambda_function_security_group" {
  name        = "${local.name}-model-access-authorizer-security-group"
  vpc_id      = local.vpc_id
  description = "security group"
  egress {
    description = "allow 443 to internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}


module "llm_gateway_rest_model_access_handler" {

  source  = "terraform-aws-modules/lambda/aws"
  version = "7.5.0"

  create_layer   = false
  create_package = false

  function_name = join("", [local.name, "-model-access-handler"])
  architectures = [local.architectures]

  vpc_subnet_ids                     = local.private_subnet_ids
  vpc_security_group_ids             = [aws_security_group.llm_gateway_rest_modelaccess_lambda_function_security_group.id]
  attach_network_policy              = true
  replace_security_groups_on_destroy = true
  replacement_security_group_ids = [local.vpc_default_security_group_id]

  environment_variables = {
    REGION : local.region,
    MODEL_ACCESS_TABLE_NAME : aws_dynamodb_table.llm_gateway_rest_model_access.name,
    DEFAULT_MODEL_ACCESS_PARAMETER_NAME : aws_ssm_parameter.llm_gateway_rest_ssm_parameter_default_model_list.name,
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
      "resources" : [local.kms_key_arn ],
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
        aws_dynamodb_table.llm_gateway_rest_model_access.arn,
      ],
    }

    ssm = {
      effect = "Allow",
      actions = [
        "ssm:GetParameter"
      ],
      resources = [
        aws_ssm_parameter.llm_gateway_rest_ssm_parameter_default_quota.arn,
        aws_ssm_parameter.llm_gateway_rest_ssm_parameter_default_model_list.arn,
      ]
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
  image_uri                  = "${data.aws_ecr_repository.modelAccessEcrRepo.repository_url}:latest"
  cloudwatch_logs_kms_key_id = local.kms_key_arn
  tags                       = local.tags
}


resource "aws_api_gateway_resource" "llm_gateway_rest_resource_model_access" {
  parent_id   = aws_api_gateway_rest_api.llm_gateway_rest_api.root_resource_id
  path_part   = "modelaccess"
  rest_api_id = aws_api_gateway_rest_api.llm_gateway_rest_api.id
}

resource "aws_api_gateway_resource" "llm_gateway_rest_resource_model_access_current_user" {
  parent_id   = aws_api_gateway_resource.llm_gateway_rest_resource_model_access.id
  path_part   = "currentuser"
  rest_api_id = aws_api_gateway_rest_api.llm_gateway_rest_api.id
}

resource "aws_api_gateway_method" "llm_gateway_rest_model_access_resource_get" {
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.llm_gateway_rest_authorizer.id
  http_method   = "GET"
  resource_id   = aws_api_gateway_resource.llm_gateway_rest_resource_model_access.id
  rest_api_id   = aws_api_gateway_rest_api.llm_gateway_rest_api.id
}

resource "aws_api_gateway_integration" "llm_gateway_rest_model_access_resource_get_integration" {
  http_method             = aws_api_gateway_method.llm_gateway_rest_model_access_resource_get.http_method
  resource_id             = aws_api_gateway_resource.llm_gateway_rest_resource_model_access.id
  rest_api_id             = aws_api_gateway_rest_api.llm_gateway_rest_api.id
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = module.llm_gateway_rest_model_access_handler.lambda_function_invoke_arn
}

resource "aws_api_gateway_method" "llm_gateway_rest_model_access_current_user_resource_get" {
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.llm_gateway_rest_authorizer.id
  http_method   = "GET"
  resource_id   = aws_api_gateway_resource.llm_gateway_rest_resource_model_access_current_user.id
  rest_api_id   = aws_api_gateway_rest_api.llm_gateway_rest_api.id
}

resource "aws_api_gateway_integration" "llm_gateway_rest_model_access_current_user_resource_get_integration" {
  http_method             = aws_api_gateway_method.llm_gateway_rest_model_access_current_user_resource_get.http_method
  resource_id             = aws_api_gateway_resource.llm_gateway_rest_resource_model_access_current_user.id
  rest_api_id             = aws_api_gateway_rest_api.llm_gateway_rest_api.id
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = module.llm_gateway_rest_model_access_handler.lambda_function_invoke_arn
}


resource "aws_api_gateway_method" "llm_gateway_rest_model_access_username_resource_post" {
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.llm_gateway_rest_authorizer.id
  http_method   = "POST"
  resource_id   = aws_api_gateway_resource.llm_gateway_rest_resource_model_access.id
  rest_api_id   = aws_api_gateway_rest_api.llm_gateway_rest_api.id
}

resource "aws_api_gateway_integration" "llm_gateway_rest_model_access_username_resource_post_integration" {
  http_method             = aws_api_gateway_method.llm_gateway_rest_model_access_username_resource_post.http_method
  resource_id             = aws_api_gateway_resource.llm_gateway_rest_resource_model_access.id
  rest_api_id             = aws_api_gateway_rest_api.llm_gateway_rest_api.id
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = module.llm_gateway_rest_model_access_handler.lambda_function_invoke_arn
}

resource "aws_api_gateway_method" "llm_gateway_rest_model_access_username_resource_delete" {
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.llm_gateway_rest_authorizer.id
  http_method   = "DELETE"
  resource_id   = aws_api_gateway_resource.llm_gateway_rest_resource_model_access.id
  rest_api_id   = aws_api_gateway_rest_api.llm_gateway_rest_api.id
}

resource "aws_api_gateway_integration" "llm_gateway_rest_model_access_username_resource_delete_integration" {
  http_method             = aws_api_gateway_method.llm_gateway_rest_model_access_username_resource_delete.http_method
  resource_id             = aws_api_gateway_resource.llm_gateway_rest_resource_model_access.id
  rest_api_id             = aws_api_gateway_rest_api.llm_gateway_rest_api.id
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = module.llm_gateway_rest_model_access_handler.lambda_function_invoke_arn
}





