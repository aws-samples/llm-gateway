locals {

  name    = var.name
  account = data.aws_caller_identity.current.account_id
  region  = var.region
  tags    = var.tags
  debug   = var.debug

  vpc_id                       = var.vpc_id
  vpc_cidr_block               = var.vpc_cidr_block
  private_subnet_ids           = var.private_subnet_ids
  vpc_default_security_group_id = var.vpc_default_security_group_id

  azs                          = slice(data.aws_availability_zones.available.names, 0, 2)
  kms_key_arn                  = var.kms_key_arn
  architectures                = var.architectures

  chatHistoryTableName         = "ChatHistory"
  chatHistoryTablePartitionKey = "id"

  apiKeyValueHashIndex            = "ApiKeyValueHashIndex"
  apiKeyTableName                 = "ApiKeyTable"
  apiKeyTablePartitionKey         = "username"
  apiKeyTableSortKey              = "api_key_name"
  apiKeyTableIndexPartitionKey    = "api_key_value_hash"
  apiKeyHandlerFunctionName       = "apiKeyHandlerFunction"
  quotaTableName                  = "QuotaTable"
  quotaTablePartitionKey          = "username"
  quotaTableSortKey               = "document_type_id"
  quotaHandlerFunctionName        = "quotaHandlerFunciton"
  modelAccessTableName            = "ModelAccessTable"
  modelAccessTablePartitionKey    = "username"
  requestDetailsTableName         = "RequestDetailsTable"
  requestDetailsTablePartitionKey = "username"
  requestDetailsTableSortKey      = "timestamp"

  user_pool_id          = var.user_pool_id
  app_client_id         = var.user_pool_app_client_id
  user_pool_domain      = var.user_pool_domain

  domain_name           = var.domain_name
  cognito_domain_prefix = var.cognito_domain_prefix

  ui_domain             = "https://${local.domain_name}"
  callback_urls = [
    "${local.ui_domain}",
    "${local.ui_domain}/oauth2/idpresponse"
  ]

  authorizer_result_ttl_in_seconds = 300

  api_endpoint_configuration = var.api_endpoint_configuration
  api_interface_endpoints = var.api_interface_endpoints

  gateway_certificate_arn = var.llmgateway_certificate_arn
  ui_certificate_arn      = var.streamlit_certificate_arn

  admin_list = var.adminList

  llmgateway_uri   = data.aws_ecr_repository.llmGatewayEcrRepo.repository_url
  quota_uri        = data.aws_ecr_repository.quotaEcrRepo.repository_url
  apikey_uri       = data.aws_ecr_repository.apiKeyEcrRepo
  model_access_uri = data.aws_ecr_repository.modelAccessEcrRepo.repository_url
  streamlit_uri    = data.aws_ecr_repository.streamlitEcrRepor.repository_url

  defaultTemp      = var.default_max_temp
  defaultMaxTokens = var.default_max_tokens

  default_quota = {
    "weekly" = "1.00"
  }
  default_model_access = {
    "model_access_list" : var.default_model_access
  }

  salt = var.salt

  llm_gateway = {
    container_name = "llm-gateway"
    container_port = 80
    host_port      = 80
    cpu            = 1024
    memory         = 2048
    desired_count  = 1
    target_group_arn = var.llmgateway_target_group_arn
    alb_security_group_id = var.llmgatereway_loadbalancer_security_group_id
    alb_dns_name = var.llmgateway_loadbalancer_dns_name
  }

  streamlit_ui = {
    container_name = "streamlit-ui"
    container_port = 8501
    host_port      = 8501
    cpu            = 1024
    memory         = 2048
    desired_count  = 1
    target_group_arn = var.streamlit_target_group_arn
    alb_security_group_id = var.streamlit_loadbalancer_security_group_id
  }

}