mock_provider "aws" {
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }

  mock_data "aws_caller_identity" {
    defaults = { account_id = "211125567571" }
  }

  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::211125567571:role/application/data-chord-dev"
    }
  }
}

variables {
  expected_account_id           = "211125567571"
  aws_region                    = "us-east-1"
  deployment_target             = "cbiit"
  environment                   = "dev"
  application_role_boundary_arn = "arn:aws:iam::211125567571:policy/cbiit-datachord-application-role-boundary"
  runtime_enabled               = false
}

run "bootstrap_creates_registry_data_and_runtime_foundation_without_network" {
  command = plan

  assert {
    condition = (
      output.ecr_repository_name == "data-chord-dev" &&
      output.ecs_cluster_name == "data-chord-dev" &&
      output.runtime_enabled == false &&
      output.ecs_service_name == null
    )
    error_message = "Bootstrap must create ECR and the ECS foundation without enabling the VPC-dependent service."
  }

  assert {
    condition = (
      output.runtime_environment.DATA_CHORD_AGENTIC_WORKERS == "5" &&
      output.runtime_environment.DATA_CHORD_MAX_ACTIVE_JOBS == "1" &&
      output.runtime_environment.DATA_CHORD_IDENTITY_SOURCE == "trusted_proxy"
    )
    error_message = "The dev runtime must retain the researched concurrency and fail-closed identity settings."
  }
}

run "runtime_uses_the_immutable_image_and_private_network" {
  command = plan

  variables {
    runtime_enabled    = true
    image_digest       = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    vpc_id             = "vpc-0123456789abcdef0"
    private_subnet_ids = ["subnet-0123456789abcdef0", "subnet-0fedcba9876543210"]
  }

  assert {
    condition = (
      aws_ecs_task_definition.app[0].cpu == "1024" &&
      aws_ecs_task_definition.app[0].memory == "4096" &&
      var.ephemeral_storage_gib == 20
    )
    error_message = "The initial dev task must use the cost-first 1 vCPU, 4 GiB, 20 GiB profile."
  }

  assert {
    condition = (
      aws_ecs_service.app[0].desired_count == 1 &&
      aws_ecs_service.app[0].network_configuration[0].assign_public_ip == false
    )
    error_message = "The initial dev service must keep one private on-demand task warm."
  }

  assert {
    condition     = jsondecode(aws_iam_role_policy.task_bedrock.policy).Statement[2].Action == "sts:GetServiceBearerToken"
    error_message = "The workload role must be able to obtain short-lived Bedrock Mantle bearer tokens."
  }
}
