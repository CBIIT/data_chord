resource "aws_ecr_repository" "app" {
  # checkov:skip=CKV_AWS_136:reason=The approved customer-managed ECR key and cross-account key policy are not yet defined;ref=CHECKOV_EXCEPTIONS.md;owner=DataChord Engineering;review=2027-02-28
  name                 = local.name_prefix
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

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
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
