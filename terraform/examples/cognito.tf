# Create Cognito User pool
resource "aws_cognito_user_pool" "llm_gateway_rest_user_pool" {

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_phone_number"
      priority = 1
    }

    recovery_mechanism {
      name     = "verified_email"
      priority = 2
    }
  }

  alias_attributes = ["preferred_username", "email"]

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  password_policy {
    temporary_password_validity_days = 7
    minimum_length                   = 8
    require_lowercase                = false
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
  }

  user_pool_add_ons {
    advanced_security_mode = "ENFORCED"
  }

  name = "${local.name}-UserPool"

  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
    email_message        = "The verification code to your new account is {####}"
    email_subject        = "Verify your new account"
    sms_message          = "The verification code to your new account is {####}"
  }
}

resource "aws_cognito_user_pool_domain" "llm_gateway_rest_user_pool_domain" {
  user_pool_id = aws_cognito_user_pool.llm_gateway_rest_user_pool.id
  domain       = local.cognito_domain_prefix
}

resource "aws_cognito_user_pool_client" "llm_gateway_rest_user_pool_client" {

  name                                 = "${local.name}-UserPoolClient"
  user_pool_id                         = aws_cognito_user_pool.llm_gateway_rest_user_pool.id
  generate_secret                      = true
  callback_urls                        = local.callback_urls
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  supported_identity_providers         = ["COGNITO", length(var.identity_providers) > 0 ? lookup(element(var.identity_providers, 0), "provider_name") : "COGNITO"]

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "hours"
  }

  refresh_token_validity = 4
  access_token_validity  = 1
  id_token_validity      = 1

  allowed_oauth_scopes = ["openid", "email"]
  depends_on =  [aws_cognito_identity_provider.llm_gateway_rest_identity_provider]
}


resource "aws_cognito_identity_provider" "llm_gateway_rest_identity_provider" {
  count         = length(var.identity_providers)
  user_pool_id  = aws_cognito_user_pool.llm_gateway_rest_user_pool.id
  provider_name = lookup(element(var.identity_providers, count.index), "provider_name")
  provider_type = lookup(element(var.identity_providers, count.index), "provider_type")

  # Optional arguments
  attribute_mapping = lookup(element(var.identity_providers, count.index), "attribute_mapping", {})
  idp_identifiers   = lookup(element(var.identity_providers, count.index), "idp_identifiers", [])
  provider_details  = lookup(element(var.identity_providers, count.index), "provider_details", {})
}