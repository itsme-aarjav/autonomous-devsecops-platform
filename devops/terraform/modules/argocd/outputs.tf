output "argocd_namespace" {
  description = "Namespace where Argo CD is deployed"
  value       = kubernetes_namespace_v1.argocd.metadata[0].name
}

output "monitoring_namespace" {
  description = "Namespace where Monitoring stack is deployed"
  value       = kubernetes_namespace_v1.monitoring.metadata[0].name
}

output "argo_rollouts_namespace" {
  description = "Namespace where Argo Rollouts controller is deployed"
  value       = kubernetes_namespace_v1.argo_rollouts.metadata[0].name
}

output "boutique_namespace" {
  description = "Namespace where Boutique application workloads are deployed"
  value       = kubernetes_namespace_v1.boutique.metadata[0].name
}

