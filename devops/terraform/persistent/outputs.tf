output "kms_key_arn" {
  description = "ARN of the Customer Managed Key (CMK)"
  value       = aws_kms_key.cmk.arn
}

output "kms_key_id" {
  description = "Key ID of the Customer Managed Key (CMK)"
  value       = aws_kms_key.cmk.key_id
}

output "ecr_repository_urls" {
  description = "Map of microservice ECR repository URLs"
  value       = module.ecr.repository_urls
}

output "secrets_manager_db_secret_arn" {
  description = "ARN of the Database Credentials Secret in Secrets Manager"
  value       = aws_secretsmanager_secret.db_credentials.arn
}

output "secrets_manager_jwt_secret_arn" {
  description = "ARN of the JWT Secret in Secrets Manager"
  value       = aws_secretsmanager_secret.jwt_secret.arn
}

output "secrets_manager_aiops_webhook_token_arn" {
  description = "ARN of the AIOps Webhook Token Secret in Secrets Manager"
  value       = aws_secretsmanager_secret.aiops_webhook_token.arn
}

output "secrets_manager_aiops_github_token_arn" {
  description = "ARN of the AIOps GitHub Token Secret in Secrets Manager"
  value       = aws_secretsmanager_secret.aiops_github_token.arn
}

output "node_diagnostics_bucket_name" {
  description = "Dedicated S3 bucket name for EKS Auto Mode NodeDiagnostic bundles"
  value       = aws_s3_bucket.node_diagnostics.id
}

output "node_diagnostics_bucket_arn" {
  description = "ARN of the dedicated S3 bucket for EKS Auto Mode NodeDiagnostic bundles"
  value       = aws_s3_bucket.node_diagnostics.arn
}

output "github_actions_ecr_publisher_role_arn" {
  description = "ARN of the IAM Role assumed by GitHub Actions to push container images"
  value       = aws_iam_role.github_actions_ecr_publisher.arn
}

output "aiops_alert_queue_url" {
  description = "URL of the AIOps Alert SQS FIFO Queue"
  value       = aws_sqs_queue.aiops_alert_queue.url
}

output "aiops_alert_queue_arn" {
  description = "ARN of the AIOps Alert SQS FIFO Queue"
  value       = aws_sqs_queue.aiops_alert_queue.arn
}

output "aiops_alert_dlq_url" {
  description = "URL of the AIOps Alert SQS FIFO Dead-Letter Queue"
  value       = aws_sqs_queue.aiops_alert_dlq.url
}

output "aiops_alert_dlq_arn" {
  description = "ARN of the AIOps Alert SQS FIFO Dead-Letter Queue"
  value       = aws_sqs_queue.aiops_alert_dlq.arn
}

output "aiops_episodes_table_name" {
  description = "Name of the DynamoDB table for AIOps episodes"
  value       = aws_dynamodb_table.aiops_episodes.name
}

output "aiops_episodes_table_arn" {
  description = "ARN of the DynamoDB table for AIOps episodes"
  value       = aws_dynamodb_table.aiops_episodes.arn
}

output "aiops_rca_table_name" {
  description = "Name of the DynamoDB table for AIOps RCA reports"
  value       = aws_dynamodb_table.aiops_rca_reports.name
}

output "aiops_rca_table_arn" {
  description = "ARN of the DynamoDB table for AIOps RCA reports"
  value       = aws_dynamodb_table.aiops_rca_reports.arn
}
