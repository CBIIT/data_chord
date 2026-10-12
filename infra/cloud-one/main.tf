data "aws_partition" "current" {}

data "aws_caller_identity" "current" {
  lifecycle {
    postcondition {
      condition     = self.account_id == var.expected_account_id
      error_message = "AWS credentials do not resolve to the target account."
    }
  }
}

locals {
  name_prefix       = "data-chord-${var.environment}"
  deployment_prefix = "datachord/${var.deployment_target}/${var.environment}"
  common_tags = {
    Project     = "data-chord"
    Environment = var.environment
    ManagedBy   = "opentofu"
  }
}

check "runtime_inputs" {
  assert {
    condition = !var.runtime_enabled || (
      var.image_digest != null &&
      var.vpc_id != null &&
      length(var.private_subnet_ids) >= 2
    )
    error_message = "runtime_enabled requires an immutable image_digest, vpc_id, and at least two private_subnet_ids."
  }
}
