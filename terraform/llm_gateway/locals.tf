locals {

  name    = var.name
  account = data.aws_caller_identity.current.account_id
  region  = var.region
  tags    = var.tags
  debug   = var.debug

  vpc_cidr                     = var.vpc_cidr
  azs                          = slice(data.aws_availability_zones.available.names, 0, 2)
  kms_key_arn                  = var.kms_key_arn
  private_gateway_loadbalancer = var.private_llm_gateway_loadbalancer
  architectures                = var.architectures

  domain_name           = var.domain_name
  cognito_domain_prefix = var.cognito_domain_prefix
  ui_domain             = "https://${local.domain_name}"
  callback_urls = [
    "${local.ui_domain}",
    "${local.ui_domain}/oauth2/idpresponse"
  ]

  gateway_certificate_arn = var.gateway_certificate_arn

  admin_list = var.adminList

  llm_gateway = {
    container_name = "llm-gateway"
    container_port = 80
    host_port      = 80
    cpu            = 1024
    memory         = 2048
    desired_count  = 1
  }

  streamlit_ui = {
    container_name = "streamlit-ui"
    container_port = 8501
    host_port      = 8501
    cpu            = 1024
    memory         = 2048
    desired_count  = 1
  }

}