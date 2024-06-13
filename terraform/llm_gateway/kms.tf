# Create project level key for encryption
module "llm_gateway_rest_kms" {
  count = local.kms_key_arn == null ? 1 : 0

  source  = "terraform-aws-modules/kms/aws"
  version = "3.0.0"


  description           = local.name
  key_usage             = "ENCRYPT_DECRYPT"
  is_enabled            = true
  enable_default_policy = true
  aliases               = [local.name]
  key_statements = [
    {
      sid = "CloudWatchLogs"
      actions = [
        "kms:Encrypt*",
        "kms:Decrypt*",
        "kms:ReEncrypt*",
        "kms:GenerateDataKey*",
        "kms:Describe*"
      ]
      resources = ["*"]

      principals = [
        {
          type        = "Service"
          identifiers = ["logs.${data.aws_region.current.name}.amazonaws.com"]
        }
      ]

      conditions = [
        {
          test     = "ArnLike"
          variable = "kms:EncryptionContext:aws:logs:arn"
          values = [
            "arn:aws:logs:${local.region}:${local.account}:log-group:*",
          ]
        }
      ]
    }
  ]
  tags = local.tags
}