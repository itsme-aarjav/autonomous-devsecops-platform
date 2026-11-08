output "cluster_name" {
  description = "The name of the EKS cluster"
  value       = aws_eks_cluster.eks.name
}

output "cluster_endpoint" {
  description = "Endpoint for the EKS control plane API server"
  value       = aws_eks_cluster.eks.endpoint
}

output "cluster_certificate_authority_data" {
  description = "Base64 encoded certificate data required to communicate with the cluster"
  value       = aws_eks_cluster.eks.certificate_authority[0].data
}

output "oidc_provider_arn" {
  description = "ARN of the OIDC provider for IRSA"
  value       = aws_iam_openid_connect_provider.eks.arn
}

output "node_role_arn" {
  description = "ARN of the EKS Auto Mode Node IAM Role"
  value       = aws_iam_role.eks_node_role.arn
}

output "cluster_security_group_id" {
  description = "Security Group ID automatically provisioned by EKS for cluster communication"
  value       = aws_eks_cluster.eks.vpc_config[0].cluster_security_group_id
}

output "auto_mode_enabled" {
  description = "Whether EKS Auto Mode is enabled for compute, storage, and networking"
  value       = true
}

output "aiops_agent_role_arn" {
  description = "ARN of the EKS Pod Identity IAM Role for Autonomous AIOps Agent"
  value       = aws_iam_role.aiops_agent_role.arn
}

output "postgres_backup_role_arn" {
  description = "ARN of the EKS Pod Identity IAM Role for PostgreSQL Database Backups"
  value       = aws_iam_role.postgres_backup_role.arn
}
