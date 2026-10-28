variable "expected_account_id" {
  description = "AWS account that owns this Cloud One deployment."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "expected_account_id must be a 12-digit AWS account id."
  }
}

variable "aws_region" {
  description = "AWS region for the deployment."
  type        = string
}

variable "deployment_target" {
  description = "Stable target name used in deployment-owned storage paths."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]*$", var.deployment_target))
    error_message = "deployment_target must be a lowercase target name."
  }
}

variable "environment" {
  description = "Deployment environment name."
  type        = string

  validation {
    condition     = contains(["dev", "qa", "staging", "prod"], var.environment)
    error_message = "environment must be dev, qa, staging, or prod."
  }
}

variable "application_role_boundary_arn" {
  description = "Foundation-owned permissions boundary applied to application roles."
  type        = string

  validation {
    condition     = can(regex("^arn:(aws|aws-us-gov):iam::${var.expected_account_id}:policy/.+$", var.application_role_boundary_arn))
    error_message = "application_role_boundary_arn must be an IAM policy in expected_account_id."
  }
}

variable "application_role_path" {
  description = "Foundation-owned IAM path for application roles."
  type        = string
  default     = "/application/"

  validation {
    condition     = can(regex("^/.+/$", var.application_role_path))
    error_message = "application_role_path must start and end with a slash."
  }
}

variable "runtime_enabled" {
  description = "Whether to create the ECS task definition and service. Bootstrap leaves this false until an image and network are ready."
  type        = bool
  default     = false
}

variable "image_digest" {
  description = "Immutable ECR image digest used by the ECS task definition."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.image_digest == null || can(regex("^sha256:[0-9a-f]{64}$", var.image_digest))
    error_message = "image_digest must be null or a sha256 digest."
  }
}

variable "vpc_id" {
  description = "Existing VPC used by the private ECS service."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition     = var.vpc_id == null || can(regex("^vpc-[0-9a-f]+$", var.vpc_id))
    error_message = "vpc_id must be null or an AWS VPC id."
  }
}

variable "private_subnet_ids" {
  description = "Existing private subnet ids used by the ECS service."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for subnet_id in var.private_subnet_ids : can(regex("^subnet-[0-9a-f]+$", subnet_id))])
    error_message = "private_subnet_ids must contain AWS subnet ids."
  }
}

variable "ingress_cidr_blocks" {
  description = "Internal CIDR ranges allowed to reach the dev preview load balancer. Empty keeps the runtime health-check-only."
  type        = list(string)
  default     = []
}

variable "internal_dev_preview_enabled" {
  description = "Whether to expose the dev service through an internal HTTP ALB with temporary shared dev identity."
  type        = bool
  default     = false
}

variable "container_cpu" {
  description = "Fargate task CPU units."
  type        = number
  default     = 1024

  validation {
    condition     = contains([256, 512, 1024, 2048, 4096, 8192, 16384], var.container_cpu)
    error_message = "container_cpu must be a supported Fargate CPU value."
  }
}

variable "container_memory" {
  description = "Fargate task memory in MiB."
  type        = number
  default     = 4096

  validation {
    condition     = var.container_memory >= 512
    error_message = "container_memory must be at least 512 MiB."
  }
}

variable "ephemeral_storage_gib" {
  description = "Fargate ephemeral storage in GiB."
  type        = number
  default     = 20

  validation {
    condition     = var.ephemeral_storage_gib >= 20 && var.ephemeral_storage_gib <= 200
    error_message = "ephemeral_storage_gib must be between 20 and 200."
  }
}

variable "desired_count" {
  description = "Initial ECS desired task count. Keep at one until multi-task behavior is qualified."
  type        = number
  default     = 1

  validation {
    condition     = var.desired_count == 1
    error_message = "desired_count must remain one until multi-task workflow behavior is qualified."
  }
}

variable "agentic_workers" {
  description = "Maximum concurrent agentic term harmonizations in one task."
  type        = number
  default     = 5

  validation {
    condition     = var.agentic_workers >= 1 && var.agentic_workers <= 100
    error_message = "agentic_workers must be between 1 and 100."
  }
}

variable "maximum_active_jobs" {
  description = "Maximum concurrent harmonization jobs in one task."
  type        = number
  default     = 1

  validation {
    condition     = var.maximum_active_jobs >= 1
    error_message = "maximum_active_jobs must be positive."
  }
}

variable "log_retention_days" {
  description = "CloudWatch application log retention."
  type        = number
  default     = 30
}
