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
  replacement_security_group_ids     = [local.vpc_replacement_security_group_ids]

  environment_variables = {
    REGION : local.region,
    MODEL_ACCESS_TABLE_NAME : aws_dynamodb_table.llm_gateway_rest_model_access.name,
    DEFAULT_MODEL_ACCESS_PARAMETER_NAME : aws_ssm_parameter.llm_gateway_rest_ssm_parameter_default_model_list.name,
    COGNITO_DOMAIN_PREFIX : local.cognito_domain_prefix
  }

  publish = true
  timeout = 900

  allowed_triggers = {
    "ALB" = {
      service    = "elasticloadbalancing"
      source_arn = aws_alb_target_group.llm_gateway_rest_model_access_handler_target_group.arn
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
  image_uri                  = "${data.aws_ecr_repository.model_access_ecr_repo.repository_url}:latest"
  cloudwatch_logs_kms_key_id = local.kms_key_arn
  tags                       = local.tags
}

resource "aws_alb_target_group" "llm_gateway_rest_model_access_handler_target_group" {
  name_prefix = local.model-access.prefix

  vpc_id               = local.vpc_id
  target_type          = "lambda"
}

resource "aws_alb_listener_rule" "llm_gateway_rest_model_access_handler_rule" {
  listener_arn = local.loadbalancer.listener_arn
  priority = local.model-access.priority
  action {
    type = "forward"
    target_group_arn = aws_alb_target_group.llm_gateway_rest_model_access_handler_target_group.arn
  }

  condition {
    host_header {
      values = [local.api_domain_name]
    }
  }

  condition {
    path_pattern {
      values = [local.model-access.path]
    }
  }

}

resource "aws_lb_target_group_attachment" "llm_gateway_rest_model_access_handler_target_group_attachment" {
  target_group_arn = aws_alb_target_group.llm_gateway_rest_model_access_handler_target_group.arn
  target_id        = module.llm_gateway_rest_model_access_handler.lambda_function_arn
}


