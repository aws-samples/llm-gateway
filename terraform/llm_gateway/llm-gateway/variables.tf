# Common Inputs

variable "name" {
  type = string
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
variable "api_key_ecr_repo" {
  type = string
}

variable "llm_gateway_ecr_repo" {
  type = string
}

variable "quota_ecr_repo" {
  type = string
}

variable "model_access_ecr_repo" {
  type = string
}

variable "streamlit_ecr_repo" {
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

variable "vpc_replacement_security_group_id" {
  type = string
}


# Load balancer related  input

variable "llm_gateway_loadbalancer_listener_arn" {
  type = string
}

variable "llm_gateway_loadbalancer_security_group_id" {
  type = string
}

variable "llm_gateway_loadbalancer_dns_name" {
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

variable "api_domain_name" {
  type = string
}

variable "ui_domain_name" {
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
