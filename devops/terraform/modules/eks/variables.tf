variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
  default     = "boutique-eks-cluster"
}

variable "vpc_id" {
  description = "VPC ID for cluster and node security group tagging"
  type        = string
  default     = ""
}

variable "control_plane_subnet_ids" {
  description = "Subnet IDs for the EKS control plane ENIs (minimum 2 AZs)"
  type        = list(string)
}

variable "worker_subnet_ids" {
  description = "Subnet IDs where worker nodes are placed"
  type        = list(string)
}

variable "allow_open_dev_eks_api" {
  description = "Temporary DEV-only override allowing 0.0.0.0/0 for EKS public API access"
  type        = bool
  default     = false
}

variable "admin_cidr_blocks" {
  description = "Authorized administrative CIDR blocks for EKS public API endpoint"
  type        = list(string)

  validation {
    condition = length(var.admin_cidr_blocks) > 0 && alltrue([
      for cidr in var.admin_cidr_blocks : can(cidrnetmask(cidr)) && (
        var.allow_open_dev_eks_api ? true : try(tonumber(split("/", cidr)[1]) > 0, false)
      )
    ])
    error_message = "admin_cidr_blocks must be a non-empty list of valid IPv4 CIDR blocks (e.g. [\"203.0.113.50/32\"]). 0.0.0.0/0 is only permitted if allow_open_dev_eks_api is set to true."
  }
}


variable "diagnostics_bucket_name" {
  description = "Dedicated S3 bucket name for EKS Auto Mode NodeDiagnostic bundles"
  type        = string
  default     = "boutique-aiops-node-diagnostics-us-east-2"
}

variable "diagnostics_kms_key_arn" {
  description = "KMS CMK Key ARN for encrypting/decrypting diagnostic bundles"
  type        = string
}

variable "aiops_alert_queue_arn" {
  description = "ARN of the AIOps Alert SQS FIFO Queue"
  type        = string
}

variable "aiops_alert_dlq_arn" {
  description = "ARN of the AIOps Alert SQS FIFO Dead-Letter Queue"
  type        = string
}

variable "aiops_episodes_table_arn" {
  description = "ARN of the DynamoDB table for AIOps episodes"
  type        = string
}

variable "aiops_rca_table_arn" {
  description = "ARN of the DynamoDB table for AIOps RCA reports"
  type        = string
}

variable "aiops_remediations_table_arn" {
  description = "ARN of the DynamoDB table for AIOps remediation proposals"
  type        = string
  default     = ""
}

variable "database_backup_bucket_name" {
  description = "Dedicated S3 bucket name for scheduled PostgreSQL backups"
  type        = string
  default     = "boutique-aiops-backups-592668326948-us-east-2"
}

variable "database_backup_bucket_arn" {
  description = "ARN of the dedicated S3 bucket for scheduled PostgreSQL backups"
  type        = string
  default     = "arn:aws:s3:::boutique-aiops-backups-592668326948-us-east-2"
}

# NOTE: Legacy on-demand / spot node group variables and disk_size have been removed.
# In EKS Auto Mode, worker scheduling and node capacity are managed dynamically via
# Auto Mode NodePools (karpenter.sh/v1) and NodeClasses (eks.amazonaws.com/v1).
