
# Common Inputs
variable "name" {
  type        = string
  default     = "llm-gateway"
  description = "Name of the project"
}

variable "region" {
  type        = string
  description = "Region in which the project is deployed"
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Key value pairs of tags to apply to resources"
}

variable "is_private_llm_gateway_loadbalancer" {
  type        = bool
  default     = true
  description = "Boolean to create a private load balancer or a public one"
}

variable "debug" {
  type    = bool
  default = false
  description = "debug logs flag"
}

#  VPC related variables
variable "vpc_cidr" {
  type        = string
  description = "VPC cidr of the vpc"
}


variable "kms_key_arn" {
  type        = string
  default     = null
  description = "KMS key Arn for the key to encrypt all resources"
}

# ECR repositories
variable "api_key_ecr_image_uri" {
  type        = string
  description = "The full image uri for the api_key lambda function"
}

variable "quota_ecr_image_uri" {
  type        = string
  description = "The full image uri for the quota function"
}

variable "model_access_ecr_image_uri" {
  type        = string
  description = "The full image uri for the model access function"
}

variable "llm_gateway_ecr_image_uri" {
  type        = string
  description = "The full image uri for the llm gateway ecs service"
}

variable "streamlit_ecr_image_uri" {
  type        = string
  description = "The full image uri for the streamlit ecs service"
}


variable "gateway_certificate_arn" {
  type        = string
  default     = null
  description = "ACM Certificate arn to be used for the Application load balancer."
}

variable "architectures" {
  type        = string
  default     = "arm64"
  description = "Platform architecture for lambda and ECS containers"
}

variable "adminList" {
  type        = string
  description = "Comma seperated list of admin users"
}

variable "salt" {
  type        = string
  description = "Random secret to use for authorizer"
}

variable "default_model_access" {
  type        = string
  description = "Comma seperated list of default allowed models "
}

variable "enabled_models" {
  type        = string
  description = "Comma seperated list of Enabled models with region"
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

variable "api_domain_name" {
  type        = string
  description = "api domain to access the Gateway"
}

variable "ui_domain_name" {
  type        = string
  description = "ui domain to access the streamlit user interface"
}

variable "cognito_domain_prefix" {
  type        = string
  description = "Cognito domain prefix for the userpool"
}

variable "identity_providers" {
  description = "Cognito Pool Identity Providers."
  type        = list(any)
  default     = []
  sensitive   = true
}