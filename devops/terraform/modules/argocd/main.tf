terraform {
  required_providers {
    kubernetes = {
      source = "hashicorp/kubernetes"
    }
    helm = {
      source = "hashicorp/helm"
    }
  }
}

# Namespaces
resource "kubernetes_namespace_v1" "argocd" {
  metadata {
    name = "argocd"
    labels = {
      "app.kubernetes.io/part-of" = "argocd"
    }
  }
}

resource "kubernetes_namespace_v1" "monitoring" {
  metadata {
    name = "monitoring"
    labels = {
      "app.kubernetes.io/part-of" = "monitoring"
    }
  }
}

resource "kubernetes_namespace_v1" "boutique" {
  metadata {
    name = "boutique"
    labels = {
      "app.kubernetes.io/part-of" = "boutique"
    }
  }
}

# NOTE: AWS Load Balancer Controller Helm release and ServiceAccount are REMOVED.
# EKS Auto Mode manages Application Load Balancer lifecycle natively via
# kubernetes_network_config.elastic_load_balancing.enabled = true and
# eks.amazonaws.com/alb IngressClass.

# ArgoCD Helm Release (Stage 3B.2)
resource "helm_release" "argocd" {
  count      = var.enable_argocd ? 1 : 0
  name       = "argocd"
  namespace  = kubernetes_namespace_v1.argocd.metadata[0].name
  repository = "https://argoproj.github.io/argo-helm"
  chart      = "argo-cd"
  version    = "10.11.6"

  create_namespace = false
  cleanup_on_fail  = true
  timeout          = 600

  values = [
    yamlencode({
      global = {
        nodeSelector = {
          "node-lifecycle" = "on-demand"
          "role"           = "core-platform"
        }
        tolerations = [
          {
            key      = "role"
            operator = "Equal"
            value    = "core-platform"
            effect   = "NoSchedule"
          }
        ]
        networkPolicy = {
          create = true
        }
      }
      server = {
        service = {
          type = "ClusterIP"
        }
        ingress = {
          enabled = false
        }
        resources = {
          requests = {
            cpu    = "100m"
            memory = "128Mi"
          }
          limits = {
            cpu    = "250m"
            memory = "256Mi"
          }
        }
      }
      repoServer = {
        resources = {
          requests = {
            cpu    = "100m"
            memory = "256Mi"
          }
          limits = {
            cpu    = "300m"
            memory = "512Mi"
          }
        }
      }
      controller = {
        resources = {
          requests = {
            cpu    = "200m"
            memory = "512Mi"
          }
          limits = {
            cpu    = "500m"
            memory = "1024Mi"
          }
        }
      }
      redis = {
        resources = {
          requests = {
            cpu    = "50m"
            memory = "64Mi"
          }
          limits = {
            cpu    = "100m"
            memory = "128Mi"
          }
        }
      }
      dex = {
        resources = {
          requests = {
            cpu    = "50m"
            memory = "64Mi"
          }
          limits = {
            cpu    = "100m"
            memory = "128Mi"
          }
        }
      }
      applicationSet = {
        resources = {
          requests = {
            cpu    = "50m"
            memory = "64Mi"
          }
          limits = {
            cpu    = "100m"
            memory = "128Mi"
          }
        }
      }
      notifications = {
        resources = {
          requests = {
            cpu    = "50m"
            memory = "64Mi"
          }
          limits = {
            cpu    = "100m"
            memory = "128Mi"
          }
        }
      }
    })
  ]

  depends_on = [kubernetes_namespace_v1.argocd]
}

# Kube-Prometheus-Stack Monitoring Release (Stage 3B.4)
resource "helm_release" "monitoring" {
  count      = var.enable_monitoring ? 1 : 0
  name       = "kube-prometheus-stack"
  namespace  = kubernetes_namespace_v1.monitoring.metadata[0].name
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "kube-prometheus-stack"
  version    = "56.21.0"

  timeout          = 600
  create_namespace = false

  values = [
    yamlencode({
      global = {
        nodeSelector = {
          "node-lifecycle" = "on-demand"
          "role"           = "core-platform"
        }
        tolerations = [
          {
            key      = "role"
            operator = "Equal"
            value    = "core-platform"
            effect   = "NoSchedule"
          }
        ]
      }
      grafana = {
        service = { type = "ClusterIP" }
        nodeSelector = {
          "node-lifecycle" = "on-demand"
          "role"           = "core-platform"
        }
        tolerations = [
          {
            key      = "role"
            operator = "Equal"
            value    = "core-platform"
            effect   = "NoSchedule"
          }
        ]
        resources = {
          requests = {
            cpu    = "100m"
            memory = "256Mi"
          }
          limits = {
            cpu    = "250m"
            memory = "512Mi"
          }
        }
      }
      prometheus = {
        service = { type = "ClusterIP" }
        prometheusSpec = {
          ruleNamespaceSelector = {}
          ruleSelector = {
            matchLabels = {
              release = "kube-prometheus-stack"
            }
          }
          nodeSelector = {
            "node-lifecycle" = "on-demand"
            "role"           = "core-platform"
          }
          tolerations = [
            {
              key      = "role"
              operator = "Equal"
              value    = "core-platform"
              effect   = "NoSchedule"
            }
          ]
          resources = {
            requests = {
              cpu    = "350m"
              memory = "1536Mi"
            }
            limits = {
              cpu    = "1000m"
              memory = "3072Mi"
            }
          }
        }
      }
      alertmanager = {
        service = { type = "ClusterIP" }
        alertmanagerSpec = {
          secrets = ["aiops-webhook-secret"]
          nodeSelector = {
            "node-lifecycle" = "on-demand"
            "role"           = "core-platform"
          }
          tolerations = [
            {
              key      = "role"
              operator = "Equal"
              value    = "core-platform"
              effect   = "NoSchedule"
            }
          ]
          resources = {
            requests = {
              cpu    = "50m"
              memory = "128Mi"
            }
            limits = {
              cpu    = "100m"
              memory = "256Mi"
            }
          }
        }
        config = {
          global = {
            resolve_timeout = "5m"
          }
          route = {
            group_by        = ["namespace", "workload", "alertname"]
            group_wait      = "10s"
            group_interval  = "30s"
            repeat_interval = "12h"
            receiver        = "null"
            routes = [
              {
                matchers = ["alertname = PodOOMKilled"]
                receiver = "aiops-webhook"
                continue = false
              }
            ]
          }
          receivers = [
            {
              name = "null"
            },
            {
              name = "aiops-webhook"
              webhook_configs = [
                {
                  url           = "http://aiops-assistant.boutique.svc.cluster.local:8080/api/v1/alerts"
                  send_resolved = true
                  http_config = {
                    authorization = {
                      type             = "Bearer"
                      credentials_file = "/etc/alertmanager/secrets/aiops-webhook-secret/token"
                    }
                  }
                }
              ]
            }
          ]
        }
      }
      prometheusOperator = {
        nodeSelector = {
          "node-lifecycle" = "on-demand"
          "role"           = "core-platform"
        }
        tolerations = [
          {
            key      = "role"
            operator = "Equal"
            value    = "core-platform"
            effect   = "NoSchedule"
          }
        ]
        resources = {
          requests = {
            cpu    = "100m"
            memory = "128Mi"
          }
          limits = {
            cpu    = "200m"
            memory = "256Mi"
          }
        }
        admissionWebhooks = {
          patch = {
            nodeSelector = {
              "node-lifecycle" = "on-demand"
              "role"           = "core-platform"
            }
            tolerations = [
              {
                key      = "role"
                operator = "Equal"
                value    = "core-platform"
                effect   = "NoSchedule"
              }
            ]
          }
        }
      }
      "kube-state-metrics" = {
        nodeSelector = {
          "node-lifecycle" = "on-demand"
          "role"           = "core-platform"
        }
        tolerations = [
          {
            key      = "role"
            operator = "Equal"
            value    = "core-platform"
            effect   = "NoSchedule"
          }
        ]
        resources = {
          requests = {
            cpu    = "50m"
            memory = "64Mi"
          }
          limits = {
            cpu    = "100m"
            memory = "128Mi"
          }
        }
      }
      "prometheus-node-exporter" = {
        tolerations = [
          {
            operator = "Exists"
          }
        ]
      }
    })
  ]

  depends_on = [kubernetes_namespace_v1.monitoring]
}

# ------------------------------------------------------------------------------
# Argo Rollouts Controller & CRDs Release (Stage 3B.4)
# ------------------------------------------------------------------------------
resource "kubernetes_namespace_v1" "argo_rollouts" {
  metadata {
    name = "argo-rollouts"
    labels = {
      "app.kubernetes.io/part-of" = "argo-rollouts"
    }
  }
}

resource "helm_release" "argo_rollouts" {
  count      = var.enable_argo_rollouts ? 1 : 0
  name       = "argo-rollouts"
  namespace  = kubernetes_namespace_v1.argo_rollouts.metadata[0].name
  repository = "https://argoproj.github.io/argo-helm"
  chart      = "argo-rollouts"
  version    = "2.37.2"

  create_namespace = false
  cleanup_on_fail  = true
  timeout          = 600

  values = [
    yamlencode({
      installCRDs = true
      controller = {
        nodeSelector = {
          "node-lifecycle" = "on-demand"
          "role"           = "core-platform"
        }
        tolerations = [
          {
            key      = "role"
            operator = "Equal"
            value    = "core-platform"
            effect   = "NoSchedule"
          }
        ]
        resources = {
          requests = {
            cpu    = "100m"
            memory = "128Mi"
          }
          limits = {
            cpu    = "200m"
            memory = "256Mi"
          }
        }
      }
    })
  ]

  depends_on = [kubernetes_namespace_v1.argo_rollouts]
}
