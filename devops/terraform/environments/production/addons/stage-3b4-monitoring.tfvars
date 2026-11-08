# ==============================================================================
# Stage 3B.4: Deploy Kube-Prometheus-Stack Monitoring & Argo Rollouts
# Preconditions: Stage 3B.2 applied, Stage 3B.3 secret sync complete (aiops-webhook-secret present).
# Scope: Deploys Kube-Prometheus-Stack Helm release & Argo Rollouts Helm release.
# ==============================================================================
enable_argocd        = true
enable_monitoring    = true
enable_argo_rollouts = true
