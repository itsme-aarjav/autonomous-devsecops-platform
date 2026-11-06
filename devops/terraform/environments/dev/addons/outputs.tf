output "argocd_namespace" {
  description = "Namespace where Argo CD is deployed"
  value       = module.argocd.argocd_namespace
}

output "monitoring_namespace" {
  description = "Namespace where Monitoring stack is deployed"
  value       = module.argocd.monitoring_namespace
}

