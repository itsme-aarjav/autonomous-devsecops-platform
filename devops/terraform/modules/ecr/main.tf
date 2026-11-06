variable "repositories" {
  description = "List of ECR repository names"
  type        = list(string)
}

variable "kms_key_arn" {
  description = "Optional KMS CMK ARN for repository encryption"
  type        = string
  default     = null
}

resource "aws_ecr_repository" "repos" {
  for_each = toset(var.repositories)

  name                 = each.value
  force_delete         = false # Protect production images
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  dynamic "encryption_configuration" {
    for_each = var.kms_key_arn != null ? [1] : []
    content {
      encryption_type = "KMS"
      kms_key         = var.kms_key_arn
    }
  }

  tags = {
    Name      = each.value
    ManagedBy = "terraform"
    Platform  = "boutique-microservices"
  }
}

# Image retention policy: keep last 10 tagged images, expire untagged after 7 days
resource "aws_ecr_lifecycle_policy" "retention" {
  for_each   = aws_ecr_repository.repos
  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images older than 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Retain maximum 10 latest tagged builds"
        selection = {
          tagStatus      = "tagged"
          tagPatternList = ["*"]
          countType      = "imageCountMoreThan"
          countNumber    = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
