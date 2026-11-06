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

variable "disk_size" {
  description = "Root disk size in GiB for worker nodes (Legacy / Fallback)"
  type        = number
  default     = 30
}

# -----------------------------------------------------------------------------
# Legacy Node Group Settings (Preserved for variable backwards-compatibility)
# In EKS Auto Mode, node provisioning is dynamically handled by Karpenter NodePools.
# -----------------------------------------------------------------------------
variable "on_demand_instance_types" {
  description = "EC2 instance types for On-Demand node pool"
  type        = list(string)
  default     = ["m7i-flex.large"]
}

variable "on_demand_desired_size" {
  description = "Desired number of On-Demand worker nodes (Legacy)"
  type        = number
  default     = 2
}

variable "on_demand_min_size" {
  description = "Minimum number of On-Demand worker nodes (Legacy)"
  type        = number
  default     = 2
}

variable "on_demand_max_size" {
  description = "Maximum number of On-Demand worker nodes (Legacy)"
  type        = number
  default     = 3
}

variable "spot_instance_types" {
  description = "EC2 instance types for Spot node pool"
  type        = list(string)
  default     = ["m7i-flex.large", "m6i.large", "c7i.large", "c6i.large"]
}

variable "spot_desired_size" {
  description = "Desired number of Spot worker nodes (Legacy)"
  type        = number
  default     = 1
}

variable "spot_min_size" {
  description = "Minimum number of Spot worker nodes (Legacy)"
  type        = number
  default     = 1
}

variable "spot_max_size" {
  description = "Maximum number of Spot worker nodes (Legacy)"
  type        = number
  default     = 5
}
