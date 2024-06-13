
# Common Inputs
variable "name" {
  type    = string
  default = "llm-gateway"
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

#  VPC related variables
variable "vpc_cidr" {
  type = string
}


variable "kms_key_arn" {
  type    = string
  default = null
}

# ECR repositories
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


variable "private_llmgateway_loadbalancer" {
  type    = bool
  default = false
}

variable "api_endpoint_configuration" {
  type = string
  validation {
    condition     = contains(["REGIONAL", "PRIVATE"], var.api_endpoint_configuration)
    error_message = "allowed values are REGIONAL or PRIVATE"
  }
}

variable "ui_certificate_arn" {
  type    = string
  default = null
}

variable "gateway_certificate_arn" {
  type    = string
  default = null
}

variable "salt" {
  type = string
}

variable "architectures" {
  type    = string
  default = "arm64"
}

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


variable "domain_name" {
  type = string
}

variable "cognito_domain_prefix" {
  type = string
}

variable "identity_providers" {
  description = "Cognito Pool Identity Providers"
  type        = list(any)
  default     = []
  sensitive   = true
}