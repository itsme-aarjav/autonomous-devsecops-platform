variable "region" {
  description = "Target AWS region"
  type        = string
  default     = "us-east-2"
}

variable "environment" {
  description = "Environment identifier"
  type        = string
  default     = "persistent"
}

variable "repositories" {
  description = "List of ECR repository names for microservices and AIOps"
  type        = list(string)
  default = [
    "boutique-frontend",
    "boutique-gateway",
    "boutique-auth",
    "boutique-aiops-assistant"
  ]
}

variable "diagnostics_bucket_name" {
  description = "Dedicated S3 bucket for EKS Auto Mode NodeDiagnostic tarballs (Never reuse TF state bucket)"
  type        = string
  default     = "boutique-aiops-node-diagnostics-us-east-2"
}

variable "diagnostics_retention_days" {
  description = "Lifecycle expiration days for uploaded node diagnostic bundles"
  type        = number
  default     = 14
}

variable "database_backup_bucket_name" {
  description = "Dedicated S3 bucket for scheduled PostgreSQL database backups (Never reuse TF state bucket)"
  type        = string
  default     = "boutique-aiops-backups-592668326948-us-east-2"
}

variable "database_backup_daily_retention_days" {
  description = "Lifecycle retention days for routine daily PostgreSQL backups under daily/ prefix"
  type        = number
  default     = 14
}

variable "legacy_secrets_kms_key_arn" {
  description = "Historical KMS CMK ARN preserving encryption for restored legacy database and JWT secrets until separately authorized migration"
  type        = string
  default     = "arn:aws:kms:us-east-2:592668326948:key/fbae32ef-8684-4aef-83b2-722fc490f95f"
}


