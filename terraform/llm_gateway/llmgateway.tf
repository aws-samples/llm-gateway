module "llm_gateway" {
  source = "./llm-gateway"
  name                                        = var.name
  region                                      = var.region

  # VPC related Local variables
  vpc_id                                      = module.vpc.vpc_id
  vpc_cidr_block                              = module.vpc.vpc_cidr_block
  vpc_default_security_group_id               = module.vpc.default_security_group_id
  private_subnet_ids                          = module.vpc.private_subnets

  # KMS related Local variables

  kms_key_arn                                 = local.kms_key_arn == null ? module.llm_gateway_rest_kms[0].key_arn : local.kms_key_arn

  # ECR Repository related Local variables
  apiKeyEcrRepo                               = var.apiKeyEcrRepo
  streamlitEcrRepo                            = var.streamlitEcrRepo
  quotaEcrRepo                                = var.quotaEcrRepo
  modelAccessEcrRepo                          = var.modelAccessEcrRepo
  llmGatewayEcrRepo                           = var.llmGatewayEcrRepo

  # Api Gateway related Local variables

  api_endpoint_configuration                  = var.api_endpoint_configuration
  api_interface_endpoints = local.api_endpoint_configuration == "REGIONAL" ? [] : [module.vpc_endpoints.endpoints["api"].id]

  # Cognito related Local variables
  user_pool_id                                = aws_cognito_user_pool.llm_gateway_rest_user_pool.id
  user_pool_app_client_id                     = aws_cognito_user_pool_client.llm_gateway_rest_user_pool_client.id
  user_pool_domain                            = aws_cognito_user_pool_domain.llm_gateway_rest_user_pool_domain.domain
  cognito_domain_prefix                       = var.cognito_domain_prefix

  # LLM Gateway related Local variables

  adminList                                   = var.adminList
  default_model_access                        = var.default_model_access
  salt                                        = var.salt
  domain_name                                 = var.domain_name

  # LLM Gateway Load balancer

  llmgatereway_loadbalancer_security_group_id = module.llmgateway_alb.security_group_id
  llmgateway_loadbalancer_dns_name            = module.llmgateway_alb.dns_name
  llmgateway_target_group_arn                 = module.llmgateway_alb.target_groups[local.llm_gateway.container_name].arn

  streamlit_loadbalancer_security_group_id    = module.streamlit_alb.security_group_id
  streamlit_target_group_arn                  = module.streamlit_alb.target_groups[local.streamlit_ui.container_name].arn



}