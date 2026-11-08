output "argocd_namespace" {
  description = "Namespace where Argo CD is deployed"
  value       = module.argocd.argocd_namespace
}

output "monitoring_namespace" {
  description = "Namespace where Monitoring stack is deployed"
  value       = module.argocd.monitoring_namespace
}

output "boutique_namespace" {
  description = "Namespace where Boutique application workloads are deployed"
  value       = module.argocd.boutique_namespace
}

output "argo_rollouts_namespace" {
  description = "Namespace where Argo Rollouts controller is deployed"
  value       = module.argocd.argo_rollouts_namespace
}

