# Common Inputs

variable "name" {
  type    = string
}

variable "region" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "debug" {
  type    = bool
  default = false
}

variable "architectures" {
  type    = string
  default = "arm64"
}

# All ECR repositories
variable "apiKeyEcrRepo" {
  type = string
}

variable "llmGatewayEcrRepo" {
  type = string
}

variable "quotaEcrRepo" {
  type = string
}

variable "modelAccessEcrRepo" {
  type = string
}

variable "streamlitEcrRepo" {
  type = string
}



# VPC Related input

variable "vpc_id" {
  type = string
}

variable "vpc_cidr_block" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "vpc_default_security_group_id" {
  type = string
}


# Load balancer related  input

variable "streamlit_certificate_arn" {
  type    = string
  default = null
}

variable "llmgateway_certificate_arn" {
  type    = string
  default = null
}

variable "streamlit_target_group_arn" {
  type = string
}

variable "streamlit_loadbalancer_security_group_id" {
  type = string
}

variable "llmgateway_target_group_arn" {
  type = string
}

variable "llmgatereway_loadbalancer_security_group_id" {
  type = string
}

variable "llmgateway_loadbalancer_dns_name" {
  type = string
}

# Cognito Input

variable "user_pool_app_client_id" {
  type = string
}
variable "user_pool_domain" {
  type = string
}
variable "user_pool_id" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

variable "domain_name" {
  type = string
}

variable "cognito_domain_prefix" {
  type = string
}

# Gateway configuration variables

variable "adminList" {
  type = string
}

variable "default_model_access" {
  type = string
}

variable "default_max_tokens" {
  type        = string
  default     = "4096"
  description = "Default Max Tokens"
}

variable "default_max_temp" {
  type        = string
  default     = "1"
  description = "Default Temperature"
}

variable "salt" {
  type = string
}

# Api Gateway Input

variable "api_endpoint_configuration" {
  type = string
  validation {
    condition     = contains(["REGIONAL", "PRIVATE"], var.api_endpoint_configuration)
    error_message = "allowed values are REGIONAL or PRIVATE"
  }
}
variable "api_interface_endpoints" {
  type = list(string)
}