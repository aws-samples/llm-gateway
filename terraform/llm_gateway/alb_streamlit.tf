module "streamlit_alb" {
  source = "terraform-aws-modules/alb/aws"
  version = "9.9.0"


  name    = "${local.name}-streamlit"
  vpc_id  = module.vpc.vpc_id
  subnets = module.vpc.public_subnets

  enable_cross_zone_load_balancing = true
  # For example only
  enable_deletion_protection = false

  # Security Group
  security_group_ingress_rules = {
    all_https = {
      from_port   = 443
      to_port     = 445
      ip_protocol = "tcp"
      description = "HTTPS web traffic"
      cidr_ipv4   = "0.0.0.0/0"
    }
  }

  security_group_egress_rules = {

    container = {
      from_port   = local.streamlit_ui.container_port
      to_port     = local.streamlit_ui.container_port
      description = "HTTPS web traffic"
      cidr_ipv4   = module.vpc.vpc_cidr_block
    }

    cognito = {
      from_port   = 443
      to_port     = 443
      description = "HTTPS web traffic"
      cidr_ipv4   = "0.0.0.0/0"
    }
  }

  listeners = {
    ex-https = {
      port            = 443
      protocol        = "HTTPS"
      ssl_policy      = "ELBSecurityPolicy-TLS13-1-2-Res-2021-06"
      certificate_arn = local.ui_certificate_arn

      fixed_response = {
        content_type = "text/plain"
        message_body = "Fixed response"
        status_code  = 200
      }


      rules = {
        streamlit-cognito = {
          actions = [
                        {
                          type                       = "authenticate-cognito"
                          session_cookie_name        = "session-${local.name}"
                          session_timeout            = 3600
                          user_pool_arn              = aws_cognito_user_pool.llm_gateway_rest_user_pool.arn
                          user_pool_client_id        = aws_cognito_user_pool_client.llm_gateway_rest_user_pool_client.id
                          user_pool_domain           = aws_cognito_user_pool_domain.llm_gateway_rest_user_pool_domain.id
                          scope                      = "openid email"
                        },
            {
              type             = "forward"
              target_group_key = local.streamlit_ui.container_name
            }
          ]

          conditions = [{
            path_pattern = {
              values = ["/", "/*"]
            }
          }]
        }
      }
    }
  }

  target_groups = {

    "${local.streamlit_ui.container_name}" = {
      port = local.streamlit_ui.container_port
      backend_protocol                  = "HTTP"
      backend_port                      = local.streamlit_ui.container_port
      target_type                       = "ip"
      deregistration_delay              = 5
      load_balancing_cross_zone_enabled = true

      health_check = {
        enabled             = true
        healthy_threshold   = 5
        interval            = 30
        matcher             = "200"
        path                = "/healthz"
        port                = "traffic-port"
        protocol            = "HTTP"
        timeout             = 5
        unhealthy_threshold = 2
      }

      # Theres nothing to attach here in this definition. Instead,
      # ECS will attach the IPs of the tasks to this target group
      create_attachment = false
    }
  }
}