variable "aws_region" {
  description = "AWS region — Mumbai for India data residency"
  type        = string
  default     = "ap-south-1"
}

variable "engagement_id" {
  description = "Unique engagement identifier (e.g. acme-banks-2026q2)"
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9-]{5,40}$", var.engagement_id))
    error_message = "engagement_id must be 5–40 lowercase alphanumeric + hyphens."
  }
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "production"
  validation {
    condition     = contains(["production", "staging", "dev"], var.environment)
    error_message = "environment must be production, staging, or dev."
  }
}

variable "vpc_cidr" {
  description = "CIDR block for the engagement VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.101.0/24", "10.0.102.0/24"]
}

variable "container_image" {
  description = "ECR image URI for the opex-api container"
  type        = string
}

variable "task_cpu" {
  description = "Fargate task CPU units (1 vCPU = 1024)"
  type        = number
  default     = 2048
}

variable "task_memory" {
  description = "Fargate task memory (MiB)"
  type        = number
  default     = 4096
}

variable "desired_count" {
  description = "Initial ECS service replica count"
  type        = number
  default     = 2
}

variable "redis_node_type" {
  description = "ElastiCache node type for cost-room filter cache"
  type        = string
  default     = "cache.t4g.medium"
}
