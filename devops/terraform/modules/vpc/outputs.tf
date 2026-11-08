output "vpc_id" {
  description = "The ID of the VPC"
  value       = aws_vpc.vpc.id
}

output "public_subnet_ids" {
  description = "List of public subnet IDs"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "List of private subnet IDs"
  value       = aws_subnet.private[*].id
}

output "nat_gateway_id" {
  description = "The ID of the NAT Gateway"
  value       = aws_nat_gateway.nat.id
}

output "s3_endpoint_id" {
  description = "The ID of the S3 Gateway VPC Endpoint"
  value       = aws_vpc_endpoint.s3.id
}

output "ecr_api_endpoint_id" {
  description = "The ID of the ECR API Interface Endpoint"
  value       = aws_vpc_endpoint.ecr_api.id
}

output "ecr_dkr_endpoint_id" {
  description = "The ID of the ECR Docker Registry Interface Endpoint"
  value       = aws_vpc_endpoint.ecr_dkr.id
}
