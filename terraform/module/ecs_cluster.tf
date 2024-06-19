
module "ecs_cluster" {
  source  = "terraform-aws-modules/ecs/aws//modules/cluster"
  version = "5.11.2"

  cluster_name              = local.name
  cloudwatch_log_group_name = "/aws/ecs/${local.name}"

  # Capacity provider
  fargate_capacity_providers = {
    FARGATE = {
      default_capacity_provider_strategy = {
        weight = 50
        base   = 20
      }
    }
    FARGATE_SPOT = {
      default_capacity_provider_strategy = {
        weight = 50
      }
    }
  }

  tags = local.tags
}