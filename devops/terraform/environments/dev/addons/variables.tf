variable "region" {
  description = "Target AWS region"
  type        = string
  default     = "us-east-2"
}

variable "environment" {
  description = "Environment identifier"
  type        = string
  default     = "dev"
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

