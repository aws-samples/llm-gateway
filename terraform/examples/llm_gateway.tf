module "llm_gateway" {
  source = "../module"
  name   = var.name
  region = var.region

  # VPC related Local variables
  vpc_id                            = module.vpc.vpc_id
  vpc_cidr_block                    = module.vpc.vpc_cidr_block
  vpc_replacement_security_group_id = module.vpc.default_security_group_id
  private_subnet_ids                = module.vpc.private_subnets

  # KMS related Local variables

  kms_key_arn = local.kms_key_arn == null ? module.llm_gateway_rest_kms[0].key_arn : local.kms_key_arn

  # ECR Repository related Local variables
  api_key_ecr_image_uri      = var.api_key_ecr_image_uri
  streamlit_ecr_image_uri    = var.streamlit_ecr_image_uri
  quota_ecr_image_uri        = var.quota_ecr_image_uri
  model_access_ecr_image_uri = var.model_access_ecr_image_uri
  llm_gateway_ecr_image_uri  = var.llm_gateway_ecr_image_uri


  # Cognito related Local variables
  user_pool_id            = aws_cognito_user_pool.llm_gateway_rest_user_pool.id
  user_pool_arn           = aws_cognito_user_pool.llm_gateway_rest_user_pool.arn
  user_pool_app_client_id = aws_cognito_user_pool_client.llm_gateway_rest_user_pool_client.id
  user_pool_domain        = aws_cognito_user_pool_domain.llm_gateway_rest_user_pool_domain.domain
  cognito_domain_prefix   = var.cognito_domain_prefix

  # LLM Gateway related Local variables

  adminList            = var.adminList
  default_model_access = var.default_model_access
  enabled_models = var.enabled_models
  salt                 = var.salt
  api_domain_name      = var.api_domain_name
  ui_domain_name       = var.ui_domain_name

  # LLM Gateway Load balancer

  llm_gateway_loadbalancer_security_group_id = module.llm_gateway_alb.security_group_id
  llm_gateway_loadbalancer_listener_arn      = module.llm_gateway_alb.listeners["https"].arn

}