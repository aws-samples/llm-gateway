resource "aws_security_group" "llm_gateway_rest_apikey_lambda_function_security_group" {
  vpc_id      = local.vpc_id
  description = "Security group for api key handler"

  egress {
    description = "Allow internet using https"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

module "llm_gateway_rest_apikey_handler" {

  source  = "terraform-aws-modules/lambda/aws"
  version = "7.5.0"

  create_layer   = false
  create_package = false

  function_name = join("", [local.name, "-apikey-handler"])
  architectures = [local.architectures]

  vpc_subnet_ids                     = local.private_subnet_ids
  vpc_security_group_ids             = [aws_security_group.llm_gateway_rest_apikey_lambda_function_security_group.id]
  attach_network_policy              = true
  replace_security_groups_on_destroy = true
  replacement_security_group_ids     = [local.vpc_replacement_security_group_ids]

  environment_variables = {
    API_KEY_TABLE_NAME : aws_dynamodb_table.llm_gateway_rest_apikey.name,
    COGNITO_DOMAIN_PREFIX : local.cognito_domain_prefix,
    REGION : local.region,
    SALT_SECRET : aws_secretsmanager_secret.llm_gateway_rest_secret_salt.name
    NON_ADMIN_ENDPOINTS : local.non_admin_endpoints,
    API_KEY_EXCLUDED_ENDPOINTS : local.api_key_excluded_endpoints,
    USER_POOL_ID : local.user_pool_id,
    APP_CLIENT_ID : local.user_pool_app_client_id,
    ADMIN_LIST : local.admin_list,
  }


  publish = true
  timeout = 900

  allowed_triggers = {
    "ALB" = {
      service    = "elasticloadbalancing"
      source_arn = aws_alb_target_group.llm_gateway_rest_apikey_handler_target_group.arn
    }
  }

  attach_policy_statements = true
  policy_statements = {

    #    api_gateway = {
    #      effect  = "Allow",
    #      actions = ["execute-api:Invoke", "execute-api:ManageConnections"],
    #      "resources" : ["arn:aws:execute-api:${local.region}:${local.account}:${aws_api_gateway_rest_api.llm_gateway_rest_api.id}/*"],
    #    }

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
  package_type = "Image"
  image_uri    = local.api_key_ecr_image_uri

  cloudwatch_logs_kms_key_id = local.kms_key_arn
  tags                       = local.tags
}

resource "aws_alb_target_group" "llm_gateway_rest_apikey_handler_target_group" {
  name_prefix = local.apikey.prefix
  vpc_id      = local.vpc_id
  target_type = "lambda"
}

resource "aws_alb_listener_rule" "llm_gateway_rest_apikey_handler_rule" {
  listener_arn = local.loadbalancer.listener_arn
  priority     = local.apikey.priority
  action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.llm_gateway_rest_apikey_handler_target_group.arn
  }

  condition {
    host_header {
      values = [local.api_domain_name]
    }
  }

  condition {
    path_pattern {
      values = [local.apikey.path]
    }
  }

}

resource "aws_alb_target_group_attachment" "llm_gateway_rest_apikey_handler_target_group_attachment" {
  target_group_arn = aws_alb_target_group.llm_gateway_rest_apikey_handler_target_group.arn
  target_id        = module.llm_gateway_rest_apikey_handler.lambda_function_arn
}