resource "aws_ecr_repository" "app" {
  # checkov:skip=CKV_AWS_136:reason=The approved customer-managed ECR key and cross-account key policy are not yet defined;ref=CHECKOV_EXCEPTIONS.md;owner=DataChord Engineering;review=2027-02-28
  count                = var.manage_image_repository ? 1 : 0
  name                 = local.image_repository_name
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = local.common_tags
}

moved {
  from = aws_ecr_repository.app
  to   = aws_ecr_repository.app[0]
}

data "aws_ecr_repository" "app" {
  count = var.manage_image_repository ? 0 : 1
  name  = local.image_repository_name
}

locals {
  image_repository_url = var.manage_image_repository ? aws_ecr_repository.app[0].repository_url : data.aws_ecr_repository.app[0].repository_url
}

resource "aws_ecr_registry_scanning_configuration" "app" {
  count = var.manage_ecr_registry_scanning ? 1 : 0

  scan_type = "ENHANCED"

  rule {
    scan_frequency = "CONTINUOUS_SCAN"

    repository_filter {
      filter      = "data-chord-*"
      filter_type = "WILDCARD"
    }
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  count      = var.manage_image_repository ? 1 : 0
  repository = aws_ecr_repository.app[0].name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Retain the newest 30 immutable images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 30
      }
      action = { type = "expire" }
    }]
  })
}

moved {
  from = aws_ecr_lifecycle_policy.app
  to   = aws_ecr_lifecycle_policy.app[0]
}
