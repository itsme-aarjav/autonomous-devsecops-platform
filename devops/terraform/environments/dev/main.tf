# Dev environment: VPC and EKS Auto Mode cluster

module "vpc" {
  source = "../../modules/vpc"

  vpc_name             = var.vpc_name
  cidr_block           = var.vpc_cidr
  region               = var.region
  cluster_name         = var.cluster_name
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  availability_zones   = var.availability_zones
}

module "eks" {
  source = "../../modules/eks"

  cluster_name             = var.cluster_name
  vpc_id                   = module.vpc.vpc_id
  control_plane_subnet_ids = module.vpc.private_subnet_ids
  worker_subnet_ids        = [module.vpc.private_subnet_ids[0]] # Workers in us-east-2a for demo co-location
  admin_cidr_blocks        = var.admin_cidr_blocks
  allow_open_dev_eks_api   = var.allow_open_dev_eks_api

  diagnostics_kms_key_arn = data.terraform_remote_state.persistent.outputs.kms_key_arn
  diagnostics_bucket_name = data.terraform_remote_state.persistent.outputs.node_diagnostics_bucket_name

  aiops_alert_queue_arn        = data.terraform_remote_state.persistent.outputs.aiops_alert_queue_arn
  aiops_alert_dlq_arn          = data.terraform_remote_state.persistent.outputs.aiops_alert_dlq_arn
  aiops_episodes_table_arn     = data.terraform_remote_state.persistent.outputs.aiops_episodes_table_arn
  aiops_rca_table_arn          = data.terraform_remote_state.persistent.outputs.aiops_rca_table_arn
  aiops_remediations_table_arn = data.terraform_remote_state.persistent.outputs.aiops_remediations_table_arn

  depends_on = [module.vpc]
}
