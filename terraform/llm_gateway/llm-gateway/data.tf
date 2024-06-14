data "aws_availability_zones" "available" {}
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "aws_ecr_repository" "api_key_ecr_repo" {
  name = var.api_key_ecr_repo
}

data "aws_ecr_repository" "quota_ecr_repo" {
  name = var.quota_ecr_repo
}

data "aws_ecr_repository" "llm_gateway_ecr_repo" {
  name = var.llm_gateway_ecr_repo
}
data "aws_ecr_repository" "model_access_ecr_repo" {
  name = var.model_access_ecr_repo
}


data "aws_ecr_repository" "streamlit_ecr_repo" {
  name = var.streamlit_ecr_repo
}


data "aws_iam_policy_document" "aws_apigateway_cloudwatch_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["apigateway.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

data "aws_iam_policy_document" "aws_apigateway_cloudwatch_policy" {
  statement {
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
      "logs:PutLogEvents",
      "logs:GetLogEvents",
      "logs:FilterLogEvents",
    ]

    resources = [
      "arn:aws:logs:${local.region}:${local.account}:log-group:*",
      "arn:aws:logs:${local.region}:${local.account}:log-group:*:log-stream:*"
    ]

  }
}

