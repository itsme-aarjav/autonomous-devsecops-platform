# Addons stage applied after the EKS cluster is provisioned

provider "kubernetes" {
  host                   = data.terraform_remote_state.dev.outputs.eks_cluster_endpoint
  cluster_ca_certificate = base64decode(data.terraform_remote_state.dev.outputs.cluster_certificate_authority_data)
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", data.terraform_remote_state.dev.outputs.eks_cluster_name]
  }
}

provider "helm" {
  kubernetes = {
    host                   = data.terraform_remote_state.dev.outputs.eks_cluster_endpoint
    cluster_ca_certificate = base64decode(data.terraform_remote_state.dev.outputs.cluster_certificate_authority_data)
    exec = {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", data.terraform_remote_state.dev.outputs.eks_cluster_name]
    }
  }
}

module "argocd" {
  source = "../../../modules/argocd"

  cluster_name      = data.terraform_remote_state.dev.outputs.eks_cluster_name
  region            = var.region
  vpc_id            = data.terraform_remote_state.dev.outputs.vpc_id
  oidc_provider_arn = data.terraform_remote_state.dev.outputs.oidc_provider_arn
}

