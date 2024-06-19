# Common Inputs
variable "name" {
  type        = string
  description = "Name of the project"
}

variable "region" {
  type        = string
  description = "AWS region in which the project is deployed"
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Key value pairs of tags to apply to resources"
}

variable "debug" {
  type    = bool
  default = false
}

variable "architectures" {
  type        = string
  default     = "arm64"
  description = "Platform architecture for lambda and ECS containers"
}

# All ECR repositories
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


# VPC Related input

variable "vpc_id" {
  type        = string
  description = "VPC id where the solution should be deployed"
}

variable "vpc_cidr_block" {
  type        = string
  description = "cidr block of the vpc where the solution should be deployed"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "private subnet ids where the solution is deployed"
}

variable "vpc_replacement_security_group_id" {
  type        = string
  description = "A dummy replacement group id to use."
}


# Load balancer related  input

variable "llm_gateway_loadbalancer_listener_arn" {
  type        = string
  description = "The load balancer listener arn where the rules will be added"
}

variable "llm_gateway_loadbalancer_security_group_id" {
  type        = string
  description = "The security group of the load balancer to whitelist ecs service security group ingress rules"
}


# Cognito Input

variable "user_pool_app_client_id" {
  type        = string
  description = "Cognito App Client id for the user pool "
}

variable "user_pool_domain" {
  type        = string
  description = "The domain of the cognito user pool"
}

variable "user_pool_id" {
  type        = string
  description = "Id of the cognito user pool"
}

variable "user_pool_arn" {
  type        = string
  description = "Arn of the cognito user pool"
}


variable "kms_key_arn" {
  type        = string
  description = "KMS key Arn for the key to encrypt all resources"
}

variable "cognito_domain_prefix" {
  type        = string
  description = "Cognito domain prefix for the userpool"
}

variable "api_domain_name" {
  type        = string
  description = "api domain to access the Gateway. For example 'api.example.com'"
}

variable "ui_domain_name" {
  type        = string
  description = "ui domain to access the streamlit user interface. For example 'ui.example.com'"
}


# Gateway configuration variables

variable "adminList" {
  type        = string
  description = "Comma seperated list of admin users"
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

variable "salt" {
  type        = string
  description = "Random secret to use for authorizer"
}
