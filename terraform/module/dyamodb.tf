resource "aws_dynamodb_table" "llm_gateway_rest_chat_history" {

  attribute {
    name = local.chat_history_table_partition_key
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  read_capacity  = 5
  write_capacity = 5
  server_side_encryption {
    enabled     = true
    kms_key_arn = local.kms_key_arn
  }

  hash_key = local.chat_history_table_partition_key
  name     = "${local.name}-${local.chat_history_table_name}"

}

resource "aws_dynamodb_table" "llm_gateway_rest_quota" {

  attribute {
    name = local.quota_table_partition_key
    type = "S"
  }
  attribute {
    name = local.quota_table_sort_key
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  read_capacity  = 5
  write_capacity = 5

  server_side_encryption {
    enabled     = true
    kms_key_arn = local.kms_key_arn
  }

  hash_key  = local.quota_table_partition_key
  range_key = local.quota_table_sort_key

  name = "${local.name}-${local.quota_table_name}"
}


resource "aws_dynamodb_table" "llm_gateway_rest_apikey" {

  attribute {
    name = local.api_key_table_partition_key
    type = "S"
  }

  attribute {
    name = local.api_key_table_sort_key
    type = "S"
  }

  attribute {
    name = local.api_key_table_index_partition_key
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  read_capacity  = 5
  write_capacity = 5

  server_side_encryption {
    enabled     = true
    kms_key_arn = local.kms_key_arn
  }

  hash_key  = local.api_key_table_partition_key
  range_key = local.api_key_table_sort_key

  name = "${local.name}-${local.api_key_table_name}"

  global_secondary_index {
    name = local.api_key_value_hash_index

    hash_key        = local.api_key_table_index_partition_key
    projection_type = "ALL"
    read_capacity   = 5
    write_capacity  = 5
  }
}


resource "aws_dynamodb_table" "llm_gateway_rest_model_access" {

  attribute {
    name = local.model_access_table_partition_key
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  read_capacity  = 5
  write_capacity = 5
  server_side_encryption {
    enabled     = true
    kms_key_arn = local.kms_key_arn
  }

  hash_key = local.model_access_table_partition_key
  name     = "${local.name}-${local.model_access_table_name}"
}


resource "aws_dynamodb_table" "llm_gateway_rest_request_details" {

  attribute {
    name = local.request_details_table_partition_key
    type = "S"
  }

  attribute {
    name = local.request_details_table_sort_key
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  read_capacity  = 5
  write_capacity = 5

  server_side_encryption {
    enabled     = true
    kms_key_arn = local.kms_key_arn
  }

  hash_key  = local.request_details_table_partition_key
  range_key = local.request_details_table_sort_key

  name = "${local.name}-${local.request_details_table_name}"


}


