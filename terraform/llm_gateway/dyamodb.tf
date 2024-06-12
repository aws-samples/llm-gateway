resource "aws_dynamodb_table" "llm_gateway_rest_chat_history" {

  attribute {
    name = local.chatHistoryTablePartitionKey
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  read_capacity = 5
  write_capacity = 5
  server_side_encryption {
    enabled = true
    kms_key_arn = local.kms_key_arn == null ? module.llm_gateway_rest_kms[0].key_arn: local.kms_key_arn
  }

  hash_key = local.chatHistoryTablePartitionKey
  name     = "${local.name}-${local.chatHistoryTableName}"

}

resource "aws_dynamodb_table" "llm_gateway_rest_quota" {

  attribute {
    name = local.quotaTablePartitionKey
    type = "S"
  }
  attribute {
    name = local.quotaTableSortKey
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  read_capacity = 5
  write_capacity = 5

  server_side_encryption {
    enabled = true
    kms_key_arn = local.kms_key_arn == null ? module.llm_gateway_rest_kms[0].key_arn: local.kms_key_arn
  }

  hash_key = local.quotaTablePartitionKey
  range_key = local.quotaTableSortKey

  name     = "${local.name}-${local.quotaTableName}"
}


resource "aws_dynamodb_table" "llm_gateway_rest_apikey" {

  attribute {
    name = local.apiKeyTablePartitionKey
    type = "S"
  }

  attribute {
    name = local.apiKeyTableSortKey
    type = "S"
  }

  attribute {
    name = local.apiKeyTableIndexPartitionKey
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  read_capacity = 5
  write_capacity = 5

  server_side_encryption {
    enabled = true
    kms_key_arn = local.kms_key_arn == null ? module.llm_gateway_rest_kms[0].key_arn: local.kms_key_arn
  }

  hash_key = local.apiKeyTablePartitionKey
  range_key = local.apiKeyTableSortKey

  name     = "${local.name}-${local.apiKeyTableName}"

  global_secondary_index {
    name            = local.apiKeyValueHashIndex

    hash_key        = local.apiKeyTableIndexPartitionKey
    projection_type = "ALL"
    read_capacity = 5
    write_capacity = 5
  }
}


resource "aws_dynamodb_table" "llm_gateway_rest_model_access" {

  attribute {
    name = local.modelAccessTablePartitionKey
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  read_capacity = 5
  write_capacity = 5
  server_side_encryption {
    enabled = true
    kms_key_arn = local.kms_key_arn == null ? module.llm_gateway_rest_kms[0].key_arn: local.kms_key_arn
  }

  hash_key = local.modelAccessTablePartitionKey
  name     = "${local.name}-${local.modelAccessTableName}"
}


resource "aws_dynamodb_table" "llm_gateway_rest_request_details" {

  attribute {
    name = local.requestDetailsTablePartitionKey
    type = "S"
  }

  attribute {
    name = local.requestDetailsTableSortKey
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  read_capacity = 5
  write_capacity = 5

  server_side_encryption {
    enabled = true
    kms_key_arn = local.kms_key_arn == null ? module.llm_gateway_rest_kms[0].key_arn: local.kms_key_arn
  }

  hash_key = local.requestDetailsTablePartitionKey
  range_key = local.requestDetailsTableSortKey

  name     = "${local.name}-${local.requestDetailsTableName}"


}


