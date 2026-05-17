output "vpc_id" {
  description = "VPC ID for the engagement"
  value       = module.vpc.vpc_id
}

output "kms_key_id" {
  description = "KMS key ID for envelope encryption"
  value       = aws_kms_key.opex.key_id
  sensitive   = true
}

output "artefact_bucket" {
  description = "S3 bucket for engagement artefacts and backups"
  value       = aws_s3_bucket.artefacts.bucket
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.opex.name
}

output "redis_endpoint" {
  description = "ElastiCache Redis endpoint"
  value       = "${aws_elasticache_cluster.opex.cache_nodes[0].address}:6379"
}

output "engagement_tags" {
  description = "Tags applied to all resources (for tear-down verification)"
  value = {
    "opex:engagement_id" = var.engagement_id
    "opex:product"       = "opex-intelligence-platform"
    "opex:environment"   = var.environment
  }
}
