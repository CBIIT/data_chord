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

  mock_resource "aws_security_group" {
    defaults = { id = "sg-0123456789abcdef0" }
  }

  mock_resource "aws_lb" {
    defaults = {
      arn      = "arn:aws:elasticloadbalancing:us-east-1:211125567571:loadbalancer/app/data-chord-dev-internal/0123456789abcdef"
      dns_name = "internal-data-chord-dev.us-east-1.elb.amazonaws.com"
    }
  }

  mock_resource "aws_lb_target_group" {
    defaults = {
      arn = "arn:aws:elasticloadbalancing:us-east-1:211125567571:targetgroup/data-chord-dev-preview/0123456789abcdef"
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
    condition = (
      jsondecode(aws_iam_role_policy.task_bedrock.policy).Statement[2].Action == "sts:GetServiceBearerToken" &&
      jsondecode(aws_iam_role_policy.task_bedrock.policy).Statement[2].Condition.StringEquals["sts:AWSServiceName"] == "bedrock.amazonaws.com"
    )
    error_message = "The workload role must be able to obtain short-lived Bedrock Mantle bearer tokens."
  }
}

run "dev_preview_uses_an_internal_alb_and_explicit_dev_identity" {
  command = plan

  variables {
    runtime_enabled              = true
    internal_dev_preview_enabled = true
    image_digest                 = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    vpc_id                       = "vpc-0123456789abcdef0"
    private_subnet_ids           = ["subnet-0123456789abcdef0", "subnet-0fedcba9876543210"]
    ingress_cidr_blocks          = ["0.0.0.0/0"]
  }

  assert {
    condition = (
      aws_lb.internal_dev[0].internal == true &&
      aws_lb.internal_dev[0].subnets == toset(var.private_subnet_ids) &&
      aws_lb_listener.internal_dev_http[0].port == 80 &&
      aws_lb_target_group.internal_dev[0].health_check[0].path == "/healthz"
    )
    error_message = "The dev preview must use an internal HTTP ALB across the approved private subnets."
  }

  assert {
    condition = (
      output.runtime_environment.DATA_CHORD_IDENTITY_SOURCE == "shared" &&
      output.runtime_environment.DEV_MODE == "true"
    )
    error_message = "The no-user dev preview must explicitly enable shared dev identity."
  }

  assert {
    condition = (
      one(aws_ecs_service.app[0].load_balancer).target_group_arn == aws_lb_target_group.internal_dev[0].arn
    )
    error_message = "The dev ECS service must register its application container with the internal target group."
  }

  assert {
    condition = (
      toset(one(aws_security_group.internal_alb[0].ingress).cidr_blocks) == toset(["0.0.0.0/0"]) &&
      toset(one(aws_security_group.task[0].ingress).security_groups) == toset([aws_security_group.internal_alb[0].id])
    )
    error_message = "The internal ALB must accept the configured client CIDRs, and only the ALB may reach the task."
  }
}
