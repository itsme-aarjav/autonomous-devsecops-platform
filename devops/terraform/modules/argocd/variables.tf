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

variable "enable_argocd" {
  description = "Enable Argo CD Helm release deployment (Stage 3B.2)"
  type        = bool
  default     = true
}

variable "enable_monitoring" {
  description = "Enable Kube-Prometheus-Stack Helm release deployment (Stage 3B.4)"
  type        = bool
  default     = false
}

variable "enable_argo_rollouts" {
  description = "Enable Argo Rollouts controller Helm release deployment (Stage 3B.4)"
  type        = bool
  default     = false
}
