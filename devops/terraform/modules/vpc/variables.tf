variable "vpc_name" {
  description = "Name of the VPC"
  type        = string
  default     = "boutique-vpc"
}

variable "cidr_block" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.1.0.0/16"
}

variable "region" {
  description = "Target AWS region"
  type        = string
  default     = "us-east-2"
}

variable "cluster_name" {
  description = "Name of the EKS cluster for resource tagging"
  type        = string
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets (minimum 2 AZs for ALB)"
  type        = list(string)
  default     = ["10.1.1.0/24", "10.1.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets (minimum 2 AZs for EKS)"
  type        = list(string)
  default     = ["10.1.10.0/24", "10.1.20.0/24"]
}

variable "availability_zones" {
  description = "List of availability zones matching the subnets"
  type        = list(string)
  default     = ["us-east-2a", "us-east-2b"]
}
