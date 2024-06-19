name   = "llm-gateway"
region = "eu-central-1"

vpc_cidr = "10.0.0.0/16"
tags     = {}

api_key_ecr_image_uri      = "123456789012.dkr.ecr.eu-central-1.amazonaws.com/apikey:latest"
model_access_ecr_image_uri = "123456789012.dkr.ecr.eu-central-1.amazonaws.com/model-access:latest"
quota_ecr_image_uri        = "123456789012.dkr.ecr.eu-central-1.amazonaws.com/quota:latest"
llm_gateway_ecr_image_uri  = "123456789012.dkr.ecr.eu-central-1.amazonaws.com/llm-gateway:latest"
streamlit_ecr_image_uri    = "123456789012.dkr.ecr.eu-central-1.amazonaws.com/streamlit:latest"

is_private_llm_gateway_loadbalancer = true
kms_key_arn                         = "<kms_key_arn>"

gateway_certificate_arn = "<certificate_arn>"

api_domain_name       = "api.example.com"
ui_domain_name        = "ui.example.com"
cognito_domain_prefix = "llm-gateway"

identity_providers    = [{
  provider_name = "github-oidc-idp"
  provider_type = "OIDC"
  attribute_mapping = {
    email    = "email"
    username = "sub"
    email_verified = "email_verified"
    fullname = "name"
    picture = "picture"
    preferred_username = "preferred_username"
    profile = "profile"
    updated_at = "updated_at"
    website = "website"
  }
  idp_identifiers = {

  }
  provider_details = {
    authorize_scopes = "openid, user"
    attributes_request_method  = "GET"
    client_id        = "github oauth app client id"
    oidc_issuer                   = "github oidc wrapper url"
    attributes_url                = "github oidc wrapper attributes url"
    authorize_url                 = "github oidc wrapper authorize url"
    token_url                     = "github oidc wrapper token url"
    jwks_uri                      = "github oidc wrapper jkws url"
  }
}
]


adminList            = "admin"
architectures        = "arm64"
debug                = false
salt                 = ""
default_max_temp     = "1"
default_max_tokens   = "4096"
default_model_access = "anthropic.claude-3-sonnet-20240229-v1:0,anthropic.claude-3-haiku-20240307-v1:0,amazon.titan-text-express-v1,cohere.embed-multilingual-v3,cohere.embed-english-v3"
enabled_models       = "us-east-1_meta.llama3-70b-instruct-v1:0,anthropic.claude-3-sonnet-20240229-v1:0,eu-central-1_anthropic.claude-3-haiku-20240307-v1:0,eu-central-1_amazon.titan-text-express-v1,eu-central-1_cohere.embed-multilingual-v3,eu-central-1_cohere.embed-english-v3"








