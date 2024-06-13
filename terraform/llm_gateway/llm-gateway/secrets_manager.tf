resource "aws_secretsmanager_secret" "llm_gateway_rest_secret_salt" {
  name       = "${local.name}-secert-salt"
  kms_key_id = local.kms_key_arn
}

resource "aws_secretsmanager_secret_version" "llm_gateway_rest_secret_salt_version" {

  secret_id = aws_secretsmanager_secret.llm_gateway_rest_secret_salt.id
  secret_string = jsonencode({
    "salt" = local.salt
  })
}


resource "aws_ssm_parameter" "llm_gateway_rest_ssm_parameter_default_quota" {
  name   = "${local.name}-ssm-parameter-quota"
  type   = "SecureString"
  value  = jsonencode(local.default_quota)
  key_id = local.kms_key_arn

}


resource "aws_ssm_parameter" "llm_gateway_rest_ssm_parameter_default_model_list" {

  name   = "${local.name}-ssm-parameter-model-access"
  type   = "SecureString"
  value  = jsonencode(local.default_model_access)
  key_id = local.kms_key_arn

}

