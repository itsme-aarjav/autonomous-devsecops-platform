data "terraform_remote_state" "dev" {
  backend = "s3"
  config = {
    bucket = "boutique-aiops-tfstate-us-east-2"
    key    = "dev/terraform.tfstate"
    region = var.region
  }
}

