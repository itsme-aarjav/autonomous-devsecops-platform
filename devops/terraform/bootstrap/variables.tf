variable "region" {
  description = "Target AWS deployment region"
  type        = string
  default     = "us-east-2"
}

variable "state_bucket_name" {
  description = "Name of the S3 remote state storage bucket"
  type        = string
  default     = "boutique-aiops-tfstate-us-east-2"
}

