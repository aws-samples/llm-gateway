# Create Cloudwatch Log Group for Rest API
resource "aws_cloudwatch_log_group" "llm_gateway_rest_log_group" {
  name              = "${local.name}-log-group"
  retention_in_days = 365
  kms_key_id        = local.kms_key_arn
  skip_destroy      = false
  tags              = local.tags
}

resource "aws_api_gateway_account" "llm_gateway_rest_api_gateway_account" {
  cloudwatch_role_arn = aws_iam_role.llm_gateway_rest_api_gateway_cloudwatch.arn
}

resource "aws_iam_role" "llm_gateway_rest_api_gateway_cloudwatch" {
  name               = "api_gateway_cloudwatch_global"
  assume_role_policy = data.aws_iam_policy_document.aws_apigateway_cloudwatch_assume_role.json
}


resource "aws_iam_role_policy" "cloudwatch" {
  name   = "default"
  role   = aws_iam_role.llm_gateway_rest_api_gateway_cloudwatch.id
  policy = data.aws_iam_policy_document.aws_apigateway_cloudwatch_policy.json
}

# Create Rest API
resource "aws_api_gateway_rest_api" "llm_gateway_rest_api" {

  name = "${local.name}-rest-api"
  lifecycle {
    create_before_destroy = true
  }

  policy = local.api_endpoint_configuration != "PRIVATE" ? null : jsonencode(
    {
      "Version" : "2012-10-17",
      "Statement" : [
        {
          "Effect" : "Allow",
          "Principal" : "*",
          "Action" : "execute-api:Invoke",
          "Resource" : [
            "*"
          ]
        }
#        {
#          "Effect" : "Deny",
#          "Principal" : "*",
#          "Action" : "execute-api:Invoke",
#          "Resource" : [
#            "*"
#          ],
#          "Condition" : {
#            "StringNotEquals": {
#              "aws:SourceVpc": local.vpc_id
#            }
#          }
#        }
      ]
  })

  dynamic "endpoint_configuration" {
    for_each = local.api_endpoint_configuration != "PRIVATE" ? [1] : []
    content {
      types = ["REGIONAL"]
    }
  }

  dynamic "endpoint_configuration" {
    for_each = local.api_endpoint_configuration == "PRIVATE" ? [1] : []
    content {
      types            = ["PRIVATE"]
      vpc_endpoint_ids = local.api_interface_endpoints
    }
  }
}

# Create Rest API Deployments
resource "aws_api_gateway_deployment" "llm_gateway_rest_api_deployment" {
  rest_api_id = aws_api_gateway_rest_api.llm_gateway_rest_api.id
  lifecycle {
    create_before_destroy = true
  }
  depends_on = [
    aws_api_gateway_integration.llm_gateway_rest_apikey_method_delete_integration,
    aws_api_gateway_integration.llm_gateway_rest_apikey_method_get_integration,
    aws_api_gateway_integration.llm_gateway_rest_apikey_method_post_integration,
    aws_api_gateway_integration.llm_gateway_rest_quota_method_delete_integration,
    aws_api_gateway_integration.llm_gateway_rest_quota_method_post_integration,
    aws_api_gateway_integration.llm_gateway_rest_quota_method_get_integration,
    aws_api_gateway_integration.llm_gateway_rest_quota_summary_method_get_integration,
    aws_api_gateway_integration.llm_gateway_rest_model_access_resource_get_integration,
    aws_api_gateway_integration.llm_gateway_rest_model_access_current_user_resource_get_integration,
    aws_api_gateway_integration.llm_gateway_rest_model_access_username_resource_delete_integration,
    aws_api_gateway_integration.llm_gateway_rest_model_access_username_resource_post_integration
  ]
}

# Create Rest API Stage
resource "aws_api_gateway_stage" "llm_gateway_rest_api_stage" {
  deployment_id = aws_api_gateway_deployment.llm_gateway_rest_api_deployment.id
  rest_api_id   = aws_api_gateway_rest_api.llm_gateway_rest_api.id
  stage_name    = "prod"

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.llm_gateway_rest_log_group.arn
    format          = "{ \"requestId\":\"$context.requestId\", \"extendedRequestId\":\"$context.extendedRequestId\",\"ip\": \"$context.identity.sourceIp\", \"caller\":\"$context.identity.caller\", \"user\":\"$context.identity.user\", \"requestTime\":\"$context.requestTime\", \"httpMethod\":\"$context.httpMethod\", \"resourcePath\":\"$context.resourcePath\", \"status\":\"$context.status\", \"protocol\":\"$context.protocol\", \"responseLength\":\"$context.responseLength\" }"
  }
  depends_on = [aws_cloudwatch_log_group.llm_gateway_rest_log_group]
}



# Create Rest API Request Validator
resource "aws_api_gateway_request_validator" "llm_gateway_rest_api_request_validator" {

  name                        = "RequestValidator"
  rest_api_id                 = aws_api_gateway_rest_api.llm_gateway_rest_api.id
  validate_request_body       = true
  validate_request_parameters = true
}

# Create Rest API Reqeust Model
resource "aws_api_gateway_model" "llm_gateway_rest_api_request_model" {

  content_type = "application/json"
  description  = "Validate LLM request body"
  name         = "requestmodel"
  rest_api_id  = aws_api_gateway_rest_api.llm_gateway_rest_api.id
  schema       = <<EOF
{
  "type": "object",
  "required": [
    "prompt",
    "parameters"
  ],
  "properties": {
    "prompt": {
      "type": "string"
    },
    "parameters": {
      "type": "object",
      "properties": {
        "temperature": {
          "type": "number"
        },
        "stop_sequences": {
          "type": "string"
        },
        "max_tokens_to_sample": {
          "type": "number"
        }
      }
    }
  }
}
EOF
}

# Create Rest API Keys
resource "aws_api_gateway_api_key" "llm_gateway_rest_api_key" {
  enabled = true
  name    = "${local.name}-ApiKey"
}



