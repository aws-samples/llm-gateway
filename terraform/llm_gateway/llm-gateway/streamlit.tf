module "streamlit" {
  source  = "terraform-aws-modules/ecs/aws//modules/service"
  version = "5.11.2"

  name        = "${local.name}-streamlit"
  cluster_arn = module.ecs_cluster.arn

  cpu    = 1024
  memory = 4096

  enable_execute_command = false
  assign_public_ip       = false
  runtime_platform = {
    operating_system_family = "LINUX"
    cpu_architecture        = upper(local.architectures)
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

    (local.streamlit_ui.container_name) = {
      cpu       = 1024
      memory    = 2048
      essential = true
      image     = local.streamlit_uri
      port_mappings = [
        {
          name          = local.streamlit_ui.container_name
          containerPort = local.streamlit_ui.container_port
          hostPort      = local.streamlit_ui.host_port
          protocol      = "tcp"
        }
      ]
      environment = [
        {
          name  = "LlmGatewayUrl"
          value = "https://${local.llm_gateway.alb_dns_name}/api/v1"
        },
        {
          name  = "ApiGatewayURL"
          value = "${aws_api_gateway_stage.llm_gateway_rest_api_stage.invoke_url}/"
        },
        {
          name  = "ApiGatewayModelAccessURL"
          value = "${aws_api_gateway_stage.llm_gateway_rest_api_stage.invoke_url}/"
        },
        {
          name  = "Region"
          value = local.region
        },
        {
          name  = "CognitoDomainPrefix"
          value = local.cognito_domain_prefix
        },
        {
          name  = "CognitoClientId"
          value = local.app_client_id
        },
        {
          name  = "AdminList"
          value = local.admin_list
        }
      ],

      # Example image used requires access to write to root filesystem
      readonly_root_filesystem = false

      #      dependencies = [{
      #        containerName = "fluent-bit"
      #        condition     = "START"
      #      }]

      enable_cloudwatch_logging = false
      log_configuration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = "/aws/ecs/${local.name}"
          awslogs-region        = local.region
          awslogs-stream-prefix = "ecs"
        }
      }

    }
  }


  load_balancer = {

    service = {
      target_group_arn = local.streamlit_ui.target_group_arn
      container_name   = local.streamlit_ui.container_name
      container_port   = local.streamlit_ui.container_port
    }
  }
  force_new_deployment = true

  subnet_ids = local.private_subnet_ids

  security_group_rules = {
    alb_ingress = {
      type                     = "ingress"
      from_port                = local.streamlit_ui.container_port
      to_port                  = local.streamlit_ui.container_port
      protocol                 = "tcp"
      description              = "Service port"
      source_security_group_id = local.streamlit_ui.alb_security_group_id
    }

    egress_all = {
      type        = "egress"
      from_port   = 0
      to_port     = 0
      protocol    = "-1"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }

  tags = local.tags
}