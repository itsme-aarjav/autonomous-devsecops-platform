# AWS KMS Customer Managed Key (CMK) for Envelope Encryption
resource "aws_kms_key" "cmk" {
  description             = "CMK for Boutique AIOps platform (State, Secrets & ECR)"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Name        = "boutique-aiops-cmk"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_kms_alias" "cmk_alias" {
  name          = "alias/boutique-aiops-key"
  target_key_id = aws_kms_key.cmk.key_id
}

# Amazon ECR Repositories for 4 Microservices (frontend, gateway, auth, aiops-assistant)
module "ecr" {
  source = "../modules/ecr"

  repositories = var.repositories
  kms_key_arn  = aws_kms_key.cmk.arn
}

# AWS Secrets Manager: Relational Database Credentials Container
resource "aws_secretsmanager_secret" "db_credentials" {
  name                    = "boutique/database/credentials"
  description             = "Database credentials for boutique microservices"
  kms_key_id              = aws_kms_key.cmk.arn
  recovery_window_in_days = 7

  tags = {
    Name        = "boutique-db-credentials"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# AWS Secrets Manager: Application JWT Secret Container
resource "aws_secretsmanager_secret" "jwt_secret" {
  name                    = "boutique/auth/jwt-secret"
  description             = "Cryptographic JWT signing secret for boutique services"
  kms_key_id              = aws_kms_key.cmk.arn
  recovery_window_in_days = 7

  tags = {
    Name        = "boutique-jwt-secret"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# AWS Secrets Manager: AIOps Alertmanager Webhook Authentication Token Container
resource "aws_secretsmanager_secret" "aiops_webhook_token" {
  name                    = "boutique/aiops/webhook-token"
  description             = "Shared authentication bearer token for Alertmanager to AIOps webhook delivery"
  kms_key_id              = aws_kms_key.cmk.arn
  recovery_window_in_days = 7

  tags = {
    Name        = "boutique-aiops-webhook-token"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# AWS Secrets Manager: AIOps GitHub Remediation Token Container
resource "aws_secretsmanager_secret" "aiops_github_token" {
  name                    = "boutique/aiops/github-token"
  description             = "GitHub Personal Access Token for AIOps autonomous GitOps PR creation and direct commits"
  kms_key_id              = aws_kms_key.cmk.arn
  recovery_window_in_days = 7

  tags = {
    Name        = "boutique-aiops-github-token"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# AWS Secrets Manager: AIOps Operator Approval Tokens Container
resource "aws_secretsmanager_secret" "aiops_approval_tokens" {
  name                    = "boutique/aiops/approval-tokens"
  description             = "Authorized operator tokens for GitOps remediation human approval and rejection"
  kms_key_id              = aws_kms_key.cmk.arn
  recovery_window_in_days = 7

  tags = {
    Name        = "boutique-aiops-approval-tokens"
    Environment = var.environment
    Purpose     = "AIOps Human Operator Approval Authentication"
    ManagedBy   = "terraform"
  }
}

# Dedicated S3 bucket for EKS Auto Mode NodeDiagnostic bundles
resource "aws_s3_bucket" "node_diagnostics" {
  bucket        = var.diagnostics_bucket_name
  force_destroy = false

  tags = {
    Name        = var.diagnostics_bucket_name
    Environment = var.environment
    Purpose     = "EKS Auto Mode NodeDiagnostic Bundles"
    ManagedBy   = "terraform"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "node_diagnostics" {
  bucket = aws_s3_bucket.node_diagnostics.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.cmk.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "node_diagnostics" {
  bucket = aws_s3_bucket.node_diagnostics.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "node_diagnostics" {
  bucket = aws_s3_bucket.node_diagnostics.id

  rule {
    id     = "expire-diagnostic-bundles"
    status = "Enabled"

    filter {}

    expiration {
      days = var.diagnostics_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }
}

resource "aws_s3_bucket_policy" "node_diagnostics_enforce_tls" {
  bucket = aws_s3_bucket.node_diagnostics.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnforceTLSRequestsOnly"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.node_diagnostics.arn,
          "${aws_s3_bucket.node_diagnostics.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}

# ------------------------------------------------------------------------------
# Dedicated S3 Bucket for Scheduled PostgreSQL Database Backups
# ------------------------------------------------------------------------------
resource "aws_s3_bucket" "database_backup" {
  bucket        = var.database_backup_bucket_name
  force_destroy = false

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Name        = var.database_backup_bucket_name
    Environment = var.environment
    Purpose     = "Scheduled 2:00 AM IST PostgreSQL Automated Backups"
    ManagedBy   = "terraform"
  }
}

resource "aws_s3_bucket_versioning" "database_backup" {
  bucket = aws_s3_bucket.database_backup.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "database_backup" {
  bucket = aws_s3_bucket.database_backup.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.cmk.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "database_backup" {
  bucket = aws_s3_bucket.database_backup.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "database_backup" {
  bucket = aws_s3_bucket.database_backup.id

  # Rule 1: Routine daily backups under daily/ expire current and noncurrent versions after 14 days
  rule {
    id     = "daily-backups-retention"
    status = "Enabled"

    filter {
      prefix = "daily/"
    }

    expiration {
      days = var.database_backup_daily_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 14
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  # Rule 2: Clean up expired object delete markers under daily/ prefix
  rule {
    id     = "daily-backups-delete-marker-cleanup"
    status = "Enabled"

    filter {
      prefix = "daily/"
    }

    expiration {
      expired_object_delete_marker = true
    }
  }

  # Rule 3: Abort incomplete multipart uploads in retained/ (NO object expiration rule)
  rule {
    id     = "retained-backups-abort-incomplete-multipart"
    status = "Enabled"

    filter {
      prefix = "retained/"
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

resource "aws_s3_bucket_policy" "database_backup_enforce_tls" {
  bucket = aws_s3_bucket.database_backup.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnforceTLSRequestsOnly"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.database_backup.arn,
          "${aws_s3_bucket.database_backup.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}

# ------------------------------------------------------------------------------
# GitHub Actions AWS OIDC Identity Provider & Least-Privilege Publishing Role
# ------------------------------------------------------------------------------
data "aws_caller_identity" "current" {}

# Read existing GitHub Actions AWS OIDC Identity Provider (Shared account resource)
data "aws_iam_openid_connect_provider" "github" {
  arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"
}

resource "aws_iam_role" "github_actions_ecr_publisher" {
  name        = "github-actions-ecr-publisher"
  description = "IAM Role assumed via WebIdentity by GitHub Actions to securely publish container images"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = data.aws_iam_openid_connect_provider.github.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
            "token.actions.githubusercontent.com:sub" = "repo:itsme-aarjav/autonomous-devsecops-platform:ref:refs/heads/main"
          }
        }
      }
    ]
  })

  tags = {
    Name        = "github-actions-ecr-publisher"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_iam_policy" "github_actions_ecr_publisher" {
  name        = "github-actions-ecr-publisher-policy"
  description = "Least-privilege ECR push permissions scoped to the Boutique repositories"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ECRAuthToken"
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken"
        ]
        Resource = "*"
      },
      {
        Sid    = "ECRPushRepositories"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:GetRepositoryPolicy",
          "ecr:DescribeRepositories",
          "ecr:ListImages",
          "ecr:DescribeImages",
          "ecr:BatchGetImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage"
        ]
        Resource = [
          for repo in var.repositories :
          "arn:aws:ecr:${var.region}:${data.aws_caller_identity.current.account_id}:repository/${repo}"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "github_actions_ecr_publisher" {
  role       = aws_iam_role.github_actions_ecr_publisher.name
  policy_arn = aws_iam_policy.github_actions_ecr_publisher.arn
}

# ------------------------------------------------------------------------------
# Autonomous AIOps Durable Alert Queue (SQS FIFO + DLQ)
# ------------------------------------------------------------------------------
resource "aws_sqs_queue" "aiops_alert_dlq" {
  name                        = "boutique-aiops-alert-dlq.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  message_retention_seconds   = 1209600 # 14 days
  kms_master_key_id           = aws_kms_key.cmk.arn

  tags = {
    Name        = "boutique-aiops-alert-dlq"
    Environment = var.environment
    Purpose     = "AIOps Alert Dead Letter Queue"
    ManagedBy   = "terraform"
  }
}

resource "aws_sqs_queue" "aiops_alert_queue" {
  name                        = "boutique-aiops-alert-queue.fifo"
  fifo_queue                  = true
  content_based_deduplication = false
  message_retention_seconds   = 1209600 # 14 days
  visibility_timeout_seconds  = 300     # 5 minutes
  receive_wait_time_seconds   = 20      # Long polling
  kms_master_key_id           = aws_kms_key.cmk.arn

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.aiops_alert_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name        = "boutique-aiops-alert-queue"
    Environment = var.environment
    Purpose     = "Durable AIOps Alert Ingestion Queue"
    ManagedBy   = "terraform"
  }
}

# ------------------------------------------------------------------------------
# Autonomous AIOps Durable State & RCA Storage (DynamoDB)
# ------------------------------------------------------------------------------
resource "aws_dynamodb_table" "aiops_episodes" {
  name         = "boutique-aiops-episodes"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "episode_id"

  attribute {
    name = "episode_id"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.cmk.arn
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name        = "boutique-aiops-episodes"
    Environment = var.environment
    Purpose     = "Durable AIOps Episode Deduplication and Lifecycle Tracking"
    ManagedBy   = "terraform"
  }
}

resource "aws_dynamodb_table" "aiops_rca_reports" {
  name         = "boutique-aiops-rca-reports"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "incident_id"

  attribute {
    name = "incident_id"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.cmk.arn
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name        = "boutique-aiops-rca-reports"
    Environment = var.environment
    Purpose     = "Durable AIOps Root Cause Analysis Persistence"
    ManagedBy   = "terraform"
  }
}

resource "aws_dynamodb_table" "aiops_remediations" {
  name         = "boutique-aiops-remediations"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "proposal_id"

  attribute {
    name = "proposal_id"
    type = "S"
  }

  attribute {
    name = "incident_id"
    type = "S"
  }

  global_secondary_index {
    name            = "incident-index"
    hash_key        = "incident_id"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.cmk.arn
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name        = "boutique-aiops-remediations"
    Environment = var.environment
    Purpose     = "Durable AIOps GitOps Remediation Proposals & Audit Trail"
    ManagedBy   = "terraform"
  }
}
