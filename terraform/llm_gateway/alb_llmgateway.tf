module "llmgateway_alb" {
  source  = "terraform-aws-modules/alb/aws"
  version = "9.9.0"

  name    = local.name
  vpc_id  = module.vpc.vpc_id
  subnets = local.private_gateway_loadbalancer ? module.vpc.private_subnets : module.vpc.public_subnets

  enable_cross_zone_load_balancing = true
  # For example only
  enable_deletion_protection = false

  # Security Group
  security_group_ingress_rules = {
    all_https = {
      from_port   = 443
      to_port     = 443
      ip_protocol = "tcp"
      description = "HTTPS web traffic"
      cidr_ipv4   = "0.0.0.0/0"
    }
  }

  security_group_egress_rules = {
    all = {
      from_port   = local.llm_gateway.container_port
      to_port     = local.llm_gateway.container_port
      description = "HTTPS web traffic"
      cidr_ipv4   = module.vpc.vpc_cidr_block
    }
  }

  listeners = {
    https = {
      port            = 443
      protocol        = "HTTPS"
      ssl_policy      = "ELBSecurityPolicy-TLS13-1-2-Res-2021-06"
      certificate_arn = local.gateway_certificate_arn

      fixed_response = {
        content_type = "text/plain"
        message_body = "Fixed response"
        status_code  = 200
      }

      rules = {
        llmgateway-forward = {
          actions = [
            {
              type             = "forward"
              target_group_key = local.llm_gateway.container_name
            }
          ]

          conditions = [{
            path_pattern = {
              values = ["/", "/*"]
            }
          }]
        },
      }
    }
  }

  target_groups = {

    "${local.llm_gateway.container_name}" = {
      port = local.llm_gateway.container_port

      backend_protocol                  = "HTTP"
      backend_port                      = local.llm_gateway.container_port
      target_type                       = "ip"
      deregistration_delay              = 5
      load_balancing_cross_zone_enabled = true

      health_check = {
        enabled             = true
        healthy_threshold   = 5
        interval            = 30
        matcher             = "200"
        path                = "/health"
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
