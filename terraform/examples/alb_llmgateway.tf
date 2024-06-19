module "llm_gateway_alb" {
  source  = "terraform-aws-modules/alb/aws"
  version = "9.9.0"

  name                             = local.private_gateway_loadbalancer ? "${local.name}-private" : "${local.name}-public"
  vpc_id                           = module.vpc.vpc_id
  internal                         = local.private_gateway_loadbalancer ? true : false
  subnets                          = local.private_gateway_loadbalancer ? module.vpc.private_subnets : module.vpc.public_subnets
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
    all_https = {
      from_port   = 443
      to_port     = 443
      ip_protocol = "tcp"
      description = "HTTPS traffic for cognito"
      cidr_ipv4   = "0.0.0.0/0"
    }

    gateway = {
      from_port   = local.llm_gateway.container_port
      to_port     = local.llm_gateway.container_port
      description = "HTTPS web traffic"
      cidr_ipv4   = module.vpc.vpc_cidr_block
    }

    streamlit = {
      from_port   = local.streamlit_ui.container_port
      to_port     = local.streamlit_ui.container_port
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
    }
  }
}
