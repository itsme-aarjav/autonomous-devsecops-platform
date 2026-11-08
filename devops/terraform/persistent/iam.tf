# Dedicated Human Operator IAM Role for Remediation Approval
# Strictly scoped role for authorized human operators (Phase 4.5 Task C / Phase 5.1).
# Background AIOps workers run under separate worker execution roles and CANNOT
# assume this role or perform remediation approval.

resource "aws_iam_role" "cloud_operator" {
  name        = "boutique-cloud-operator"
  description = "Dedicated IAM role for authorized human operators to review, approve, and reject GitOps remediations"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowAuthorizedPrincipalsAssumeRole"
        Effect = "Allow"
        Principal = {
          AWS = [
            "arn:aws:iam::${data.aws_caller_identity.current.account_id}:user/terra-admin"
          ]
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name        = "boutique-cloud-operator"
    Environment = var.environment
    Purpose     = "AIOps Human Operator Remediation Approval and Governance"
    ManagedBy   = "terraform"
  }
}

resource "aws_iam_policy" "cloud_operator_policy" {
  name        = "boutique-cloud-operator-remediation-policy"
  description = "Scoped permissions for human operators: DynamoDB atomic status updates, KMS CMK decrypt, and token verification"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBRemediationAuditAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:UpdateItem",
          "dynamodb:PutItem"
        ]
        Resource = [
          aws_dynamodb_table.aiops_remediations.arn,
          "${aws_dynamodb_table.aiops_remediations.arn}/index/*"
        ]
      },
      {
        Sid    = "KMSDecryptionAccess"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey",
          "kms:GenerateDataKey"
        ]
        Resource = aws_kms_key.cmk.arn
      },
      {
        Sid    = "SecretsManagerOperatorTokenRead"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [
          aws_secretsmanager_secret.aiops_approval_tokens.arn,
          aws_secretsmanager_secret.aiops_github_token.arn
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "cloud_operator_attach" {
  role       = aws_iam_role.cloud_operator.name
  policy_arn = aws_iam_policy.cloud_operator_policy.arn
}
