data "aws_availability_zones" "available" {}
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "aws_ecr_repository" "apiKeyEcrRepo" {
  name = var.apiKeyEcrRepo
}

data "aws_ecr_repository" "quotaEcrRepo" {
  name = var.quotaEcrRepo
}

data "aws_ecr_repository" "llmGatewayEcrRepo" {
  name = var.llmGatewayEcrRepo
}
data "aws_ecr_repository" "modelAccessEcrRepo" {
  name = var.modelAccessEcrRepo
}


data "aws_ecr_repository" "streamlitEcrRepor" {
  name = var.streamlitEcrRepo
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

    resources = ["arn:aws:logs:*:*:*"]
  }
}

