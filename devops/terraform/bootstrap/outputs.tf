output "state_bucket_name" {
  description = "The name of the S3 remote state bucket"
  value       = aws_s3_bucket.state_bucket.id
}

output "state_bucket_arn" {
  description = "The ARN of the S3 remote state bucket"
  value       = aws_s3_bucket.state_bucket.arn
}

output "state_bucket_region" {
  description = "The region of the S3 remote state bucket"
  value       = var.region
}

