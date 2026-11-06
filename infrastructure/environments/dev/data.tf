# Read outputs from the persistent foundation layer (ECR, KMS, Secrets Manager)
# In initial local validation before applying persistent state, fallback values are supported.
data "terraform_remote_state" "persistent" {
  backend = "s3"

  config = {
    bucket       = "boutique-aiops-tfstate-us-east-2"
    key          = "persistent/terraform.tfstate"
    region       = var.region
    use_lockfile = true
  }

  defaults = {
    kms_key_arn                   = "arn:aws:kms:us-east-2:123456789012:key/placeholder"
    node_diagnostics_bucket_name  = "boutique-aiops-node-diagnostics-us-east-2"
    secrets_manager_db_secret_arn = "arn:aws:secretsmanager:us-east-2:123456789012:secret:boutique/database/credentials"
    aiops_alert_queue_url         = "https://sqs.us-east-2.amazonaws.com/123456789012/boutique-aiops-alert-queue.fifo"
    aiops_alert_queue_arn         = "arn:aws:sqs:us-east-2:123456789012:boutique-aiops-alert-queue.fifo"
    aiops_alert_dlq_url           = "https://sqs.us-east-2.amazonaws.com/123456789012/boutique-aiops-alert-dlq.fifo"
    aiops_alert_dlq_arn           = "arn:aws:sqs:us-east-2:123456789012:boutique-aiops-alert-dlq.fifo"
    aiops_episodes_table_name     = "boutique-aiops-episodes"
    aiops_episodes_table_arn      = "arn:aws:dynamodb:us-east-2:123456789012:table/boutique-aiops-episodes"
    aiops_rca_table_name          = "boutique-aiops-rca-reports"
    aiops_rca_table_arn           = "arn:aws:dynamodb:us-east-2:123456789012:table/boutique-aiops-rca-reports"
  }
}
