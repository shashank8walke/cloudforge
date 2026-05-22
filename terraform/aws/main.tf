terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

# ─── Variables ────────────────────────────────────────────────────────────────

variable "region" {
  description = "AWS region to deploy resources into"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t2.micro"
}

variable "project_name" {
  description = "Unique name for this CloudForge lab (used to name all resources)"
  type        = string
}

variable "ami_id" {
  description = "Amazon Machine Image ID. Defaults to Amazon Linux 2 in us-east-1."
  type        = string
  default     = "ami-0c02fb55956c7d316"
}

variable "tags" {
  description = "Additional key-value tags to apply to every resource"
  type        = map(string)
  default     = {}
}

# ─── Provider ─────────────────────────────────────────────────────────────────

provider "aws" {
  region = var.region
}

# ─── Locals ───────────────────────────────────────────────────────────────────
# Merge caller-supplied tags with the standard CloudForge tags once here;
# every resource references local.common_tags so there is a single source of truth.

locals {
  common_tags = merge(
    var.tags,
    {
      Project   = var.project_name
      ManagedBy = "cloudforge"
      Provider  = "aws"
    }
  )
}

# ─── Random suffix for globally-unique S3 bucket name ─────────────────────────
# keepers ties the suffix to project_name so the same project always generates
# the same suffix within a given Terraform state, preventing bucket drift.

resource "random_id" "bucket_suffix" {
  byte_length = 4

  keepers = {
    project_name = var.project_name
  }
}

# ─── EC2 Instance ─────────────────────────────────────────────────────────────

resource "aws_instance" "lab" {
  ami           = var.ami_id
  instance_type = var.instance_type

  # Ensure a public IP is assigned so smoke tests can reach the instance.
  associate_public_ip_address = true

  user_data = <<-EOF
    #!/bin/bash
    set -euo pipefail
    yum update -y
    yum install -y python3 python3-pip
    echo "cloudforge-ready" | tee /var/log/cloudforge-ready.log
  EOF

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-instance"
  })
}

# ─── S3 Bucket ────────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "lab" {
  # Bucket names must be globally unique; the 8-char hex suffix guarantees that.
  bucket = "${var.project_name}-${random_id.bucket_suffix.hex}"

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-bucket"
  })
}

# Block all public access — this bucket stores test artefacts, not public data.
resource "aws_s3_bucket_public_access_block" "lab" {
  bucket = aws_s3_bucket.lab.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ─── Outputs ──────────────────────────────────────────────────────────────────

output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.lab.id
}

output "public_ip" {
  description = "Public IPv4 address of the EC2 instance"
  value       = aws_instance.lab.public_ip
}

output "bucket_name" {
  description = "Name of the S3 artefact bucket"
  value       = aws_s3_bucket.lab.id
}

output "region" {
  description = "AWS region the lab was deployed into"
  value       = var.region
}

output "project_name" {
  description = "Project name passed in at apply time"
  value       = var.project_name
}
