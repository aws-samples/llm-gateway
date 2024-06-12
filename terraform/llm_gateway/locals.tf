locals {

  name = var.name
  account = data.aws_caller_identity.current.account_id
  region  = var.region
  tags   = var.tags
  debug  = var.debug



  vpc_cidr = var.vpc_cidr
  azs      = slice(data.aws_availability_zones.available.names, 0, 2)
  kms_key_arn = var.kms_key_arn
  private_gateway_loadbalancer = var.private_gateway_loadbalancer
  architectures = var.architectures

  chatHistoryTableName = "ChatHistory"
  chatHistoryTablePartitionKey = "id"

  apiKeyValueHashIndex = "ApiKeyValueHashIndex"
  apiKeyTableName = "ApiKeyTable"
  apiKeyTablePartitionKey = "username"
  apiKeyTableSortKey = "api_key_name"
  apiKeyTableIndexPartitionKey = "api_key_value_hash"
  apiKeyHandlerFunctionName = "apiKeyHandlerFunction"
  quotaTableName = "QuotaTable"
  quotaTablePartitionKey = "username"
  quotaTableSortKey = "document_type_id"
  quotaHandlerFunctionName = "quotaHandlerFunciton"
  modelAccessTableName = "ModelAccessTable"
  modelAccessTablePartitionKey = "username"
  requestDetailsTableName = "RequestDetailsTable"
  requestDetailsTablePartitionKey = "username"
  requestDetailsTableSortKey = "timestamp"

  domain_name = var.domain_name
  cognito_domain_prefix = var.cognito_domain_prefix
  ui_domain = "https://${local.domain_name}"
  callback_urls = [
    "${local.ui_domain}",
    "${local.ui_domain}/oauth2/idpresponse"
  ]

  authorizer_result_ttl_in_seconds = 0

#  github_client_id = var.github_client_id
#  github_client_secret = var.github_client_secret
#
#  attributes_url    = var.attributes_url
#  authorize_url     = var.authorize_url
#  jwks_uri =  var.jwks_uri
#  oidc_issuer= var.oidc_issuer
#  token_url = var.token_url

  api_endpoint_configuration          = var.api_endpoint_configuration

  gateway_certificate_arn = var.gateway_certificate_arn
  ui_certificate_arn = var.ui_certificate_arn

  admin_list =  var.adminList

  llmgateway_uri = data.aws_ecr_repository.llmGatewayEcrRepo.repository_url
  quota_uri = data.aws_ecr_repository.quotaEcrRepo.repository_url
  apikey_uri = data.aws_ecr_repository.apiKeyEcrRepo
  model_access_uri = data.aws_ecr_repository.modelAccessEcrRepo.repository_url
  streamlit_uri = data.aws_ecr_repository.streamlitEcrRepor.repository_url


  defaultTemp =var.default_max_temp
  defaultMaxTokens = var.default_max_tokens

  default_quota = {
    "weekly" = "1.00"
  }
  default_model_access = {
    "model_access_list": var.default_model_access
  }

  salt = var.salt
  llm_gateway = {
    container_name = "llm-gateway"
    container_port = 80
    host_port = 80
    cpu = 1024
    memory = 2048
    desired_count = 1
  }

  streamlit_ui = {
    container_name = "streamlit-ui"
    container_port = 8501
    host_port = 8501
    cpu = 1024
    memory = 2048
    desired_count = 1
  }

}