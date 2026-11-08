# ==============================================================================
# Stage 3B.2: Bootstrap Kubernetes Namespaces & Deploy Argo CD
# Preconditions: EKS Cluster ACTIVE, NodePools platform-on-demand Ready.
# Scope: Creates argocd, monitoring, boutique, argo-rollouts namespaces.
#        Deploys Argo CD Helm release onto platform-on-demand pool.
#        Monitoring and Rollouts are deferred to Stage 3B.4 (after secret sync).
# ==============================================================================
enable_argocd        = true
enable_monitoring    = false
enable_argo_rollouts = false
