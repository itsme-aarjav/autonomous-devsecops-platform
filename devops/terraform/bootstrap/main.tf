terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # NOTE: Two-Phase Bootstrap Initialization Protocol
  # To prevent circular dependency during initial provisioning of the state bucket,
  # this root module defaults to local backend state.
  #
  # Fresh account (State bucket does not exist):
  #   1. terraform init
  #   2. terraform plan -out=bootstrap.tfplan
  #   3. terraform apply bootstrap.tfplan
  #   4. cp backend.tf.example backend.tf
  #   5. terraform init -migrate-state
  #
  # Existing environment (State bucket already exists):
  #   1. cp backend.tf.example backend.tf
  #   2. terraform init
}

provider "aws" {
  region = var.region
}

# Remote state bucket
resource "aws_s3_bucket" "state_bucket" {
  bucket        = var.state_bucket_name
  force_destroy = false

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Name        = var.state_bucket_name
    Environment = "bootstrap"
    ManagedBy   = "terraform"
    Purpose     = "Terraform Remote State and Lockfile Storage"
  }
}

# Enable versioning for state rollback protection
resource "aws_s3_bucket_versioning" "versioning" {
  bucket = aws_s3_bucket.state_bucket.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Default server-side encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "encryption" {
  bucket = aws_s3_bucket.state_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block public access
resource "aws_s3_bucket_public_access_block" "public_access" {
  bucket = aws_s3_bucket.state_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Abort failed uploads and expire stale state versions
resource "aws_s3_bucket_lifecycle_configuration" "lifecycle" {
  bucket = aws_s3_bucket.state_bucket.id

  rule {
    id     = "abort-incomplete-multipart-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

# Enforce HTTPS-only transport
resource "aws_s3_bucket_policy" "enforce_tls" {
  bucket = aws_s3_bucket.state_bucket.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnforceTLSRequestsOnly"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.state_bucket.arn,
          "${aws_s3_bucket.state_bucket.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.public_access]
}
