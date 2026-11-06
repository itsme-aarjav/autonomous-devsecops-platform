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

variable "vpc_name" {
  description = "Name of the VPC"
  type        = string
  default     = "boutique-dev-vpc"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.1.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDRs (minimum 2 AZs for ALB requirement)"
  type        = list(string)
  default     = ["10.1.1.0/24", "10.1.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "Private subnet CIDRs (minimum 2 AZs for EKS requirement)"
  type        = list(string)
  default     = ["10.1.10.0/24", "10.1.20.0/24"]
}

variable "availability_zones" {
  description = "Availability zones for subnets"
  type        = list(string)
  default     = ["us-east-2a", "us-east-2b"]
}

variable "cluster_name" {
  description = "Name of the EKS cluster"
  type        = string
  default     = "boutique-dev-eks"
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

# -----------------------------------------------------------------------------
# On-Demand Node Group Settings (Core Platform Services)
# -----------------------------------------------------------------------------
variable "on_demand_instance_types" {
  description = "Instance types for On-Demand node group"
  type        = list(string)
  default     = ["m7i-flex.large"]
}

variable "on_demand_desired_size" {
  description = "Desired number of On-Demand nodes (Option B requires 2 nodes for core workloads)"
  type        = number
  default     = 2
}

variable "on_demand_min_size" {
  description = "Minimum number of On-Demand nodes (Option B requires 2 nodes)"
  type        = number
  default     = 2
}

variable "on_demand_max_size" {
  description = "Maximum number of On-Demand nodes"
  type        = number
  default     = 3
}

# -----------------------------------------------------------------------------
# Spot Node Group Settings (Stateless Microservices)
# -----------------------------------------------------------------------------
variable "spot_instance_types" {
  description = "Instance types for Spot node group"
  type        = list(string)
  default     = ["m7i-flex.large"]
}

variable "spot_desired_size" {
  description = "Desired number of Spot nodes"
  type        = number
  default     = 1
}

variable "spot_min_size" {
  description = "Minimum number of Spot nodes"
  type        = number
  default     = 1
}

variable "spot_max_size" {
  description = "Maximum number of Spot nodes"
  type        = number
  default     = 5
}

