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

variable "admin_cidr_blocks" {
  description = "Authorized administrative CIDR blocks for EKS public API endpoint"
  type        = list(string)

  validation {
    condition = length(var.admin_cidr_blocks) > 0 && alltrue([
      for cidr in var.admin_cidr_blocks : can(cidrnetmask(cidr)) && try(tonumber(split("/", cidr)[1]) > 0, false)
    ])
    error_message = "admin_cidr_blocks must be a non-empty list of valid IPv4 CIDR blocks (e.g. [\"203.0.113.50/32\"]). IPv6 prefixes and 0.0.0.0/0 are not permitted."
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

# NOTE: Legacy on-demand / spot node group variables and disk_size have been removed.
# In EKS Auto Mode, worker scheduling and node capacity are managed dynamically via
# Auto Mode NodePools (karpenter.sh/v1) and NodeClasses (eks.amazonaws.com/v1).
