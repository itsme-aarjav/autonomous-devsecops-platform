data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# EKS cluster control plane role
resource "aws_iam_role" "eks_cluster_role" {
  name = "${var.cluster_name}-cluster-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "eks.amazonaws.com"
      }
      Action = [
        "sts:AssumeRole",
        "sts:TagSession"
      ]
    }]
  })

  tags = {
    Name      = "${var.cluster_name}-cluster-role"
    ManagedBy = "terraform"
  }
}

# Auto Mode requires these 5 cluster-level AWS managed policies:
resource "aws_iam_role_policy_attachment" "cluster_policy" {
  role       = aws_iam_role.eks_cluster_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_iam_role_policy_attachment" "cluster_compute_policy" {
  role       = aws_iam_role.eks_cluster_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSComputePolicy"
}

resource "aws_iam_role_policy_attachment" "cluster_block_storage_policy" {
  role       = aws_iam_role.eks_cluster_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSBlockStoragePolicyV2"
}

resource "aws_iam_role_policy_attachment" "cluster_load_balancing_policy" {
  role       = aws_iam_role.eks_cluster_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSLoadBalancingPolicy"
}

resource "aws_iam_role_policy_attachment" "cluster_networking_policy" {
  role       = aws_iam_role.eks_cluster_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSNetworkingPolicy"
}

# EKS Auto Mode node role
resource "aws_iam_role" "eks_node_role" {
  name = "${var.cluster_name}-node-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = {
    Name      = "${var.cluster_name}-node-role"
    ManagedBy = "terraform"
  }
}

resource "aws_iam_role_policy_attachment" "node_minimal_policy" {
  role       = aws_iam_role.eks_node_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodeMinimalPolicy"
}

# NOTE: AmazonEKS_CNI_Policy is intentionally removed. EKS Auto Mode manages
# the VPC CNI at the control plane level via AmazonEKSNetworkingPolicy;
# worker nodes require only AmazonEKSWorkerNodeMinimalPolicy.

resource "aws_iam_role_policy_attachment" "node_ecr_pull_policy" {
  role       = aws_iam_role.eks_node_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPullOnly"
}

# EKS cluster with Auto Mode enabled (Kubernetes 1.36)
resource "aws_eks_cluster" "eks" {
  name     = var.cluster_name
  role_arn = aws_iam_role.eks_cluster_role.arn
  version  = "1.36"

  # Disable legacy self-managed add-on bootstrapping
  bootstrap_self_managed_addons = false

  access_config {
    authentication_mode                         = "API_AND_CONFIG_MAP"
    bootstrap_cluster_creator_admin_permissions = true
  }

  vpc_config {
    subnet_ids              = var.control_plane_subnet_ids # Spans at least 2 private subnets across 2 AZs
    endpoint_private_access = true                         # Private VPC internal communication
    endpoint_public_access  = true                         # Public API access
    public_access_cidrs     = var.admin_cidr_blocks        # Strictly allowlisted admin CIDRs (no 0.0.0.0/0)
  }

  # EKS Auto Mode Compute Configuration (Managed Karpenter Engine)
  compute_config {
    enabled = true
    # Retain built-in "system" pool for critical kube-system pods (CoreDNS, kube-proxy).
    # "general-purpose" is disabled because custom NodePools handle platform & application workloads.
    node_pools    = ["system"]
    node_role_arn = aws_iam_role.eks_node_role.arn
  }

  # EKS Auto Mode Storage Configuration (Native EBS CSI Provisioner: ebs.csi.eks.amazonaws.com)
  storage_config {
    block_storage {
      enabled = true
    }
  }

  # EKS Auto Mode Networking & Elastic Load Balancing Configuration (Native ELB Controller: eks.amazonaws.com/alb)
  kubernetes_network_config {
    elastic_load_balancing {
      enabled = true
    }
  }

  enabled_cluster_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]

  depends_on = [
    aws_iam_role_policy_attachment.cluster_policy,
    aws_iam_role_policy_attachment.cluster_compute_policy,
    aws_iam_role_policy_attachment.cluster_block_storage_policy,
    aws_iam_role_policy_attachment.cluster_load_balancing_policy,
    aws_iam_role_policy_attachment.cluster_networking_policy
  ]

  tags = {
    Name                     = var.cluster_name
    "karpenter.sh/discovery" = var.cluster_name
    ManagedBy                = "terraform"
  }
}

# Tag cluster security group for Auto Mode / Karpenter discovery
resource "aws_ec2_tag" "cluster_sg_karpenter_discovery" {
  resource_id = aws_eks_cluster.eks.vpc_config[0].cluster_security_group_id
  key         = "karpenter.sh/discovery"
  value       = var.cluster_name
}

# EKS Auto Mode natively owns and automatically provisions the node role's access entry
# (type: EC2) and its associated AmazonEKSAutoNodePolicy at cluster creation via compute_config.
# No explicit aws_eks_access_entry or aws_eks_access_policy_association is required.

# IAM OIDC provider for IRSA and workload identity
data "tls_certificate" "eks" {
  url = aws_eks_cluster.eks.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "eks" {
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks.certificates[0].sha1_fingerprint]
  url             = aws_eks_cluster.eks.identity[0].oidc[0].issuer

  tags = {
    Name      = "${var.cluster_name}-oidc-provider"
    ManagedBy = "terraform"
  }
}

# IAM role for AIOps agent via EKS Pod Identity
resource "aws_iam_role" "aiops_agent_role" {
  name = "${var.cluster_name}-aiops-agent-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "pods.eks.amazonaws.com"
      }
      Action = [
        "sts:AssumeRole",
        "sts:TagSession"
      ]
      Condition = {
        StringEquals = {
          "aws:RequestTag/eks-cluster-arn"            = aws_eks_cluster.eks.arn
          "aws:RequestTag/kubernetes-namespace"       = "boutique"
          "aws:RequestTag/kubernetes-service-account" = "aiops-assistant"
        }
      }
    }]
  })

  tags = {
    Name      = "${var.cluster_name}-aiops-agent-role"
    ManagedBy = "terraform"
  }
}

resource "aws_iam_role_policy" "aiops_agent_policy" {
  name = "${var.cluster_name}-aiops-agent-policy"
  role = aws_iam_role.aiops_agent_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DiagnosticsS3ObjectAccess"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject"
        ]
        Resource = "arn:aws:s3:::${var.diagnostics_bucket_name}/nodediagnostics/*"
      },
      {
        Sid      = "DiagnosticsS3BucketList"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = "arn:aws:s3:::${var.diagnostics_bucket_name}"
        Condition = {
          StringLike = {
            "s3:prefix" = ["nodediagnostics/*", "nodediagnostics/"]
          }
        }
      },
      {
        Sid    = "DiagnosticsKMSAccess"
        Effect = "Allow"
        Action = [
          "kms:GenerateDataKey",
          "kms:Decrypt",
          "kms:DescribeKey"
        ]
        Resource = var.diagnostics_kms_key_arn
      },
      {
        Sid    = "BedrockConverseInference"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = [
          # Dedicated US Cross-Region Inference Profiles (Claude Sonnet 5.5, Sonnet 5, Haiku 4.5)
          "arn:aws:bedrock:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:inference-profile/us.anthropic.claude-sonnet-5-5",
          "arn:aws:bedrock:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:inference-profile/us.anthropic.claude-sonnet-5",
          "arn:aws:bedrock:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
          # Exact Foundation Model ARNs for destination regions (us-east-1, us-east-2, us-west-2)
          "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-5-5",
          "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-sonnet-5-5",
          "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-sonnet-5-5",
          "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-5",
          "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-sonnet-5",
          "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-sonnet-5",
          "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
          "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
          "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
          "arn:aws:bedrock:us-east-2::foundation-model/amazon.nova-lite-v1:0",
          "arn:aws:bedrock:us-east-2::foundation-model/amazon.nova-micro-v1:0",
          "arn:aws:bedrock:us-east-2::foundation-model/amazon.nova-pro-v1:0"
        ]
      },
      {
        Sid    = "AIOpsAlertQueueAccess"
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:ChangeMessageVisibility",
          "sqs:GetQueueUrl"
        ]
        Resource = [
          var.aiops_alert_queue_arn,
          var.aiops_alert_dlq_arn
        ]
      },
      {
        Sid    = "AIOpsDynamoDBStateAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:BatchGetItem"
        ]
        Resource = compact([
          var.aiops_episodes_table_arn,
          "${var.aiops_episodes_table_arn}/index/*",
          var.aiops_rca_table_arn,
          "${var.aiops_rca_table_arn}/index/*",
          var.aiops_remediations_table_arn,
          var.aiops_remediations_table_arn != "" ? "${var.aiops_remediations_table_arn}/index/*" : ""
        ])
      }
    ]
  })
}

resource "aws_eks_pod_identity_association" "aiops_agent" {
  cluster_name    = aws_eks_cluster.eks.name
  namespace       = "boutique"
  service_account = "aiops-assistant"
  role_arn        = aws_iam_role.aiops_agent_role.arn
}

# PostgreSQL backup identity
resource "aws_iam_role" "postgres_backup_role" {
  name        = "${var.cluster_name}-postgres-backup-role"
  description = "Dedicated least-privilege IAM role for PostgreSQL S3/KMS backup CronJob via EKS Pod Identity"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "pods.eks.amazonaws.com"
      }
      Action = [
        "sts:AssumeRole",
        "sts:TagSession"
      ]
      Condition = {
        StringEquals = {
          "aws:RequestTag/eks-cluster-arn"            = aws_eks_cluster.eks.arn
          "aws:RequestTag/kubernetes-namespace"       = "boutique"
          "aws:RequestTag/kubernetes-service-account" = "postgres-backup"
        }
      }
    }]
  })

  tags = {
    Name      = "${var.cluster_name}-postgres-backup-role"
    ManagedBy = "terraform"
  }
}

resource "aws_iam_role_policy" "postgres_backup_policy" {
  name = "boutique-postgres-backup-policy"
  role = aws_iam_role.postgres_backup_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "PostgresBackupS3Access"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          var.database_backup_bucket_arn,
          "${var.database_backup_bucket_arn}/backups/*"
        ]
      },
      {
        Sid    = "PostgresBackupKMSAccess"
        Effect = "Allow"
        Action = [
          "kms:GenerateDataKey",
          "kms:Decrypt",
          "kms:DescribeKey"
        ]
        Resource = var.diagnostics_kms_key_arn
      }
    ]
  })
}

resource "aws_eks_pod_identity_association" "postgres_backup" {
  cluster_name    = aws_eks_cluster.eks.name
  namespace       = "boutique"
  service_account = "postgres-backup"
  role_arn        = aws_iam_role.postgres_backup_role.arn
}

# EKS Auto Mode
# In EKS Auto Mode (compute_config.enabled = true), CoreDNS, kube-proxy, and the
# EKS Pod Identity Agent are natively built-in and automatically managed by AWS
# as system-level components directly on the Bottlerocket worker node architecture.
# Explicit aws_eks_addon declarations are intentionally omitted to avoid duplicate
# management loops, resource collisions, and version-skew compatibility issues.
