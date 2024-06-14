locals {

  name    = var.name
  account = data.aws_caller_identity.current.account_id
  region  = var.region
  tags    = var.tags
  debug   = var.debug

  vpc_id                        = var.vpc_id
  vpc_cidr_block                = var.vpc_cidr_block
  private_subnet_ids            = var.private_subnet_ids
  vpc_replacement_security_group_ids = var.vpc_replacement_security_group_id

  azs           = slice(data.aws_availability_zones.available.names, 0, 2)
  kms_key_arn   = var.kms_key_arn
  architectures = var.architectures

  chat_history_table_name         = "ChatHistory"
  chat_history_table_partition_key = "id"

  api_key_value_hash_index            = "ApiKeyValueHashIndex"
  api_key_table_name                 = "ApiKeyTable"
  api_key_table_partition_key         = "username"
  api_key_table_sort_key              = "api_key_name"
  api_key_table_index_partition_key    = "api_key_value_hash"
  api_key_handler_function_name       = "apiKeyHandlerFunction"
  quota_table_name                  = "QuotaTable"
  quota_table_partition_key          = "username"
  quota_table_sort_key               = "document_type_id"
  quota_handler_function_name        = "quotaHandlerFunciton"
  model_access_table_name            = "ModelAccessTable"
  model_access_table_partition_key    = "username"
  request_details_table_name         = "RequestDetailsTable"
  request_details_table_partition_key = "username"
  request_details_table_sort_key      = "timestamp"

  user_pool_arn     = var.user_pool_id
  user_pool_app_client_id    = var.user_pool_app_client_id
  user_pool_domain = var.user_pool_domain

  api_domain_name       = var.api_domain_name
  ui_domain_name        = var.ui_domain_name

  cognito_domain_prefix = var.cognito_domain_prefix

  admin_list = var.adminList

  llm_gateway_uri   = data.aws_ecr_repository.llm_gateway_ecr_repo.repository_url
  quota_uri        = data.aws_ecr_repository.quota_ecr_repo.repository_url
  apikey_uri       = data.aws_ecr_repository.api_key_ecr_repo
  model_access_uri = data.aws_ecr_repository.model_access_ecr_repo.repository_url
  streamlit_uri    = data.aws_ecr_repository.streamlit_ecr_repo.repository_url

  defaultTemp      = var.default_max_temp
  defaultMaxTokens = var.default_max_tokens

  default_quota = {
    "weekly" = "1.00"
  }
  default_model_access = {
    "model_access_list" : var.default_model_access
  }

  salt = var.salt

  loadbalancer = {
    listener_arn          = var.llm_gateway_loadbalancer_listener_arn
    alb_security_group_id = var.llm_gateway_loadbalancer_security_group_id
    alb_dns_name          = var.llm_gateway_loadbalancer_dns_name
  }

  apikey = {
    name = "apikey"
    prefix = "apikey"
    priority= 20
    path = "/apikey/*"
  }

  quota = {
    name = "quota"
    prefix = "quota"
    priority= 30
    path = "/modelaccess/*"
  }

  model-access = {
    name = "model-access"
    prefix="modela"
    priority= 40
    path = "/modelaccess/*"
  }

  llm_gateway = {
    name     = "llm-gateway"
    prefix ="gatewa"
    priority = 50
    path     = "/api/v1*"
    container_name = "llm-gateway"
    container_port = 80
    host_port      = 80
    cpu            = 1024
    memory         = 2048
    desired_count  = 1
  }

  streamlit_ui = {
    name = "streamlit_ui"
    prefix = "stream"
    priority = 60
    path     = "/*"
    container_name = "streamlit-ui"
    container_port = 8501
    host_port      = 8501
    cpu            = 1024
    memory         = 2048
    desired_count  = 1
  }

}