terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "s3" {
    # Populated at init: -backend-config=backend.hcl
    # bucket = "opex-tfstate-<client>"
    # key    = "opex-analyzer/terraform.tfstate"
    # region = "ap-south-1"
    # encrypt = true
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      "opex:engagement_id" = var.engagement_id
      "opex:product"       = "opex-intelligence-platform"
      "opex:environment"   = var.environment
      "opex:managed_by"    = "terraform"
    }
  }
}

# ── VPC ─────────────────────────────────────────────────────────────────────
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "opex-${var.engagement_id}"
  cidr = var.vpc_cidr

  azs             = ["${var.aws_region}a", "${var.aws_region}b"]
  private_subnets = var.private_subnet_cidrs
  public_subnets  = var.public_subnet_cidrs

  enable_nat_gateway   = true
  single_nat_gateway   = var.environment != "production"
  enable_dns_hostnames = true
  enable_dns_support   = true
}

# ── KMS ─────────────────────────────────────────────────────────────────────
resource "aws_kms_key" "opex" {
  description             = "OpEx Intelligence Platform — ${var.engagement_id}"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.kms_policy.json
}

resource "aws_kms_alias" "opex" {
  name          = "alias/opex-${var.engagement_id}"
  target_key_id = aws_kms_key.opex.key_id
}

data "aws_iam_policy_document" "kms_policy" {
  statement {
    sid       = "Enable IAM User Permissions"
    effect    = "Allow"
    principals { type = "AWS"; identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"] }
    actions   = ["kms:*"]
    resources = ["*"]
  }
  statement {
    sid       = "Allow ECS Task Role"
    effect    = "Allow"
    principals { type = "AWS"; identifiers = [aws_iam_role.ecs_task.arn] }
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = ["*"]
  }
}

data "aws_caller_identity" "current" {}

# ── S3 — artefact & backup bucket ───────────────────────────────────────────
resource "aws_s3_bucket" "artefacts" {
  bucket        = "opex-artefacts-${var.engagement_id}-${data.aws_caller_identity.current.account_id}"
  force_destroy = false
}

resource "aws_s3_bucket_versioning" "artefacts" {
  bucket = aws_s3_bucket.artefacts.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artefacts" {
  bucket = aws_s3_bucket.artefacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.opex.arn
    }
  }
}

resource "aws_s3_bucket_public_access_block" "artefacts" {
  bucket                  = aws_s3_bucket.artefacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "artefacts" {
  bucket = aws_s3_bucket.artefacts.id
  rule {
    id     = "engagement-retention"
    status = "Enabled"
    filter { prefix = "backups/" }
    expiration { days = 14 }
  }
}

# ── ECS Cluster ─────────────────────────────────────────────────────────────
resource "aws_ecs_cluster" "opex" {
  name = "opex-${var.engagement_id}"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "opex" {
  cluster_name       = aws_ecs_cluster.opex.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]
  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1
  }
}

# ── IAM — ECS task role ──────────────────────────────────────────────────────
resource "aws_iam_role" "ecs_task" {
  name = "opex-ecs-task-${var.engagement_id}"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals { type = "Service"; identifiers = ["ecs-tasks.amazonaws.com"] }
  }
}

resource "aws_iam_role_policy" "ecs_task_policy" {
  role   = aws_iam_role.ecs_task.id
  policy = data.aws_iam_policy_document.ecs_task_policy.json
}

data "aws_iam_policy_document" "ecs_task_policy" {
  statement {
    sid     = "S3Access"
    actions = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
    resources = [
      aws_s3_bucket.artefacts.arn,
      "${aws_s3_bucket.artefacts.arn}/*",
    ]
  }
  statement {
    sid     = "KMSAccess"
    actions = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.opex.arn]
  }
  statement {
    sid     = "SecretsManager"
    actions = ["secretsmanager:GetSecretValue"]
    resources = ["arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:opex/${var.engagement_id}/*"]
  }
}

# ── ECS Task Definition ──────────────────────────────────────────────────────
resource "aws_ecs_task_definition" "opex_api" {
  family                   = "opex-api-${var.engagement_id}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.ecs_task.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "opex-api"
    image     = var.container_image
    essential = true
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    environment = [
      { name = "ENGAGEMENT_ID", value = var.engagement_id },
      { name = "AWS_REGION",    value = var.aws_region },
      { name = "S3_BUCKET",     value = aws_s3_bucket.artefacts.bucket },
      { name = "KMS_KEY_ID",    value = aws_kms_key.opex.key_id },
      { name = "REDIS_URL",     value = "redis://${aws_elasticache_cluster.opex.cache_nodes[0].address}:6379/0" },
    ]
    secrets = [
      { name = "ANTHROPIC_API_KEY", valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:opex/${var.engagement_id}/anthropic_api_key" },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = "/ecs/opex-${var.engagement_id}"
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "api"
      }
    }
  }])
}

resource "aws_cloudwatch_log_group" "opex" {
  name              = "/ecs/opex-${var.engagement_id}"
  retention_in_days = 90
  kms_key_id        = aws_kms_key.opex.arn
}

# ── ElastiCache (Redis) — cost-room filter cache ────────────────────────────
resource "aws_elasticache_subnet_group" "opex" {
  name       = "opex-${var.engagement_id}"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_elasticache_cluster" "opex" {
  cluster_id           = "opex-${substr(var.engagement_id, 0, 16)}"
  engine               = "redis"
  node_type            = var.redis_node_type
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.opex.name
  security_group_ids   = [aws_security_group.redis.id]
}

resource "aws_security_group" "redis" {
  name   = "opex-redis-${var.engagement_id}"
  vpc_id = module.vpc.vpc_id
  ingress {
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── ECS Service ──────────────────────────────────────────────────────────────
resource "aws_security_group" "ecs_service" {
  name   = "opex-ecs-svc-${var.engagement_id}"
  vpc_id = module.vpc.vpc_id
  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_ecs_service" "opex_api" {
  name            = "opex-api"
  cluster         = aws_ecs_cluster.opex.id
  task_definition = aws_ecs_task_definition.opex_api.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = module.vpc.private_subnets
    security_groups  = [aws_security_group.ecs_service.id]
    assign_public_ip = false
  }

  lifecycle { ignore_changes = [desired_count] }
}
