module "ecs" {
  source  = "terraform-aws-modules/ecs/aws//modules/service"
  version = "5.11.2"

  name        = local.name
  cluster_arn = module.ecs_cluster.arn

  cpu           = local.llm_gateway.cpu
  memory        = local.llm_gateway.memory
  desired_count = local.llm_gateway.desired_count

  # Enables ECS Exec
  enable_execute_command = false
  assign_public_ip       = false
  runtime_platform = {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }

  # Container definition(s)
  container_definitions = {


    #    fluent-bit = {
    #      cpu       = 512
    #      memory    = 1024
    #      essential = true
    #      image     = nonsensitive(data.aws_ssm_parameter.fluentbit.value)
    #      firelens_configuration = {
    #        type = "fluentbit"
    #      }
    #      memory_reservation = 50
    #      user               = "0"
    #
    #    }

    (local.llm_gateway.container_name) = {
      cpu       = 512
      memory    = 1024
      essential = true
      image     = local.llmgateway_uri
      runtime_platform = {
        operating_system_family = "LINUX"
        cpu_architecture        = upper(local.architectures)
      }
      environment = [
        {

          name  = "CHAT_HISTORY_TABLE_NAME"
          value = aws_dynamodb_table.llm_gateway_rest_chat_history.name
        },
        {

          name  = "DEFAULT_TEMP"
          value = local.defaultTemp
        },
        {

          name  = "DEFAULT_MAX_TOKENS"
          value = local.defaultMaxTokens
        },
        {

          name  = "REGION"
          value = local.region
        },
        {

          name  = "COGNITO_DOMAIN_PREFIX"
          value = local.cognito_domain_prefix
        },
        {

          name  = "API_KEY_TABLE_NAME"
          value = aws_dynamodb_table.llm_gateway_rest_apikey.name
        },
        {

          name  = "SALT_SECRET"
          value = aws_secretsmanager_secret.llm_gateway_rest_secret_salt.name
        },
        {

          name  = "USER_POOL_ID"
          value = local.user_pool_id,
        },
        {

          name  = "APP_CLIENT_ID"
          value = local.app_client_id
        },
        {

          name  = "QUOTA_TABLE_NAME"
          value = aws_dynamodb_table.llm_gateway_rest_quota.name
        },
        {

          name  = "REQUEST_DETAILS_TABLE_NAME"
          value = aws_dynamodb_table.llm_gateway_rest_request_details.name
        },
        {

          name  = "MODEL_ACCESS_TABLE_NAME"
          value = aws_dynamodb_table.llm_gateway_rest_model_access.name
        },
        {

          name  = "DEFAULT_QUOTA_PARAMETER_NAME"
          value = aws_ssm_parameter.llm_gateway_rest_ssm_parameter_default_quota.name
        },
        {

          name  = "DEFAULT_MODEL_ACCESS_PARAMETER_NAME"
          value = aws_ssm_parameter.llm_gateway_rest_ssm_parameter_default_model_list.name
        },
        {

          name  = "DEBUG"
          value = local.debug
        }
      ]
      port_mappings = [
        {
          name          = local.llm_gateway.container_name
          containerPort = local.llm_gateway.container_port
          hostPort      = local.llm_gateway.host_port
          protocol      = "tcp"
        }
      ]

      # Example image used requires access to write to root filesystem
      readonly_root_filesystem = false

      #      dependencies = [{
      #        containerName = "fluent-bit"
      #        condition     = "START"
      #      }]

      enable_cloudwatch_logging = true
      log_configuration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = "/aws/ecs/${local.name}"
          awslogs-region        = local.region
          awslogs-stream-prefix = "ecs"
          awslogs-create-group  = "true"
        }
      }
    }
  }


  load_balancer = {
    service = {
      target_group_arn = local.llm_gateway.target_group_arn
      container_name   = local.llm_gateway.container_name
      container_port   = local.llm_gateway.container_port
    }
  }

  subnet_ids = local.private_subnet_ids

  tasks_iam_role_statements = [
    {
      actions = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
      "logs:PutLogEvents", ]
      resources = ["*"]
    },
    {
      effect    = "Allow",
      actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      resources = ["*"]
    },
    {
      effect  = "Allow",
      actions = ["execute-api:Invoke", "execute-api:ManageConnections"],
      "resources" : [
        "arn:aws:execute-api:${local.region}:${local.account}:${aws_api_gateway_rest_api.llm_gateway_rest_api.arn}/*"
      ],
    },
    {
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
        aws_dynamodb_table.llm_gateway_rest_quota.arn,
        aws_dynamodb_table.llm_gateway_rest_chat_history.arn,
        aws_dynamodb_table.llm_gateway_rest_model_access.arn,
        aws_dynamodb_table.llm_gateway_rest_request_details.arn,
        "${aws_dynamodb_table.llm_gateway_rest_apikey.arn}/index/*"
      ],
    },
    {
      effect = "Allow",
      actions = [
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:ReEncrypt*",
        "kms:GenerateDataKey*",
        "kms:DescribeKey"
      ],
      "resources" : [local.kms_key_arn ],
    },
    {
      effect = "Allow",
      actions = [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      resources = [aws_secretsmanager_secret.llm_gateway_rest_secret_salt.arn]
    },
    {
      effect = "Allow",
      actions = [
        "ssm:GetParameter",
      ],
      resources = [
        aws_ssm_parameter.llm_gateway_rest_ssm_parameter_default_quota.arn,
        aws_ssm_parameter.llm_gateway_rest_ssm_parameter_default_model_list.arn,
      ]
    }
  ]

  task_exec_iam_statements = [
    {
      actions = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
      "logs:PutLogEvents", ]
      resources = ["*"]
    }
  ]

  security_group_rules = {

    alb_ingress = {
      type        = "ingress"
      from_port   = local.llm_gateway.container_port
      to_port     = local.llm_gateway.container_port
      protocol    = "tcp"
      description = "Service port"
      source_security_group_id = local.llm_gateway.alb_security_group_id
    }

    egress_all = {
      type        = "egress"
      from_port   = 443
      to_port     = 443
      protocol    = "tcp"
      description = "Allow https"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }

  tags = local.tags
}