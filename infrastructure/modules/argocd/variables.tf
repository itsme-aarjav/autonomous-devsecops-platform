variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
}

variable "region" {
  description = "AWS region"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID (optional for Auto Mode)"
  type        = string
  default     = ""
}

variable "oidc_provider_arn" {
  description = "OIDC provider ARN for IRSA"
  type        = string
  default     = ""
}

variable "lbc_role_arn" {
  description = "IAM role ARN for the AWS Load Balancer Controller (Legacy / Deprecated in EKS Auto Mode)"
  type        = string
  default     = ""
}
