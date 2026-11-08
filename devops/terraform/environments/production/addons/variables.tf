variable "region" {
  description = "Target AWS region"
  type        = string
  default     = "us-east-2"
}

variable "environment" {
  description = "Environment identifier"
  type        = string
  default     = "production"
}

variable "enable_argocd" {
  description = "Enable Argo CD Helm release"
  type        = bool
  default     = true
}

variable "enable_monitoring" {
  description = "Enable monitoring Helm release"
  type        = bool
  default     = true
}

variable "enable_argo_rollouts" {
  description = "Enable Argo Rollouts Helm release"
  type        = bool
  default     = true
}

