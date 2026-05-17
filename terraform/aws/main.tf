terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# ─── Variables ────────────────────────────────────────────────────────────────

variable "lab_name" {
  description = "Unique identifier for this test lab"
  type        = string
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "ami_id" {
  description = "AMI ID for lab instances (Amazon Linux 2023 default)"
  type        = string
  default     = "ami-0c02fb55956c7d316"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.micro"
}

variable "instance_count" {
  description = "Number of lab instances to provision"
  type        = number
  default     = 1
}

variable "vpc_cidr" {
  description = "CIDR block for the lab VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnets" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24"]
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# ─── Provider ─────────────────────────────────────────────────────────────────

provider "aws" {
  region = var.region
}

# ─── Networking ───────────────────────────────────────────────────────────────

resource "aws_vpc" "lab" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(var.tags, { Name = "${var.lab_name}-vpc" })
}

resource "aws_internet_gateway" "lab" {
  vpc_id = aws_vpc.lab.id
  tags   = merge(var.tags, { Name = "${var.lab_name}-igw" })
}

resource "aws_subnet" "public" {
  count                   = length(var.public_subnets)
  vpc_id                  = aws_vpc.lab.id
  cidr_block              = var.public_subnets[count.index]
  map_public_ip_on_launch = true
  availability_zone       = data.aws_availability_zones.available.names[count.index % length(data.aws_availability_zones.available.names)]

  tags = merge(var.tags, { Name = "${var.lab_name}-public-${count.index}" })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.lab.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.lab.id
  }

  tags = merge(var.tags, { Name = "${var.lab_name}-rt-public" })
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

data "aws_availability_zones" "available" {
  state = "available"
}

# ─── Security Group ───────────────────────────────────────────────────────────

resource "aws_security_group" "lab" {
  name        = "${var.lab_name}-sg"
  description = "CloudForge lab security group"
  vpc_id      = aws_vpc.lab.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.lab_name}-sg" })
}

# ─── EC2 Instances ────────────────────────────────────────────────────────────

resource "aws_instance" "lab" {
  count                  = var.instance_count
  ami                    = var.ami_id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public[count.index % length(aws_subnet.public)].id
  vpc_security_group_ids = [aws_security_group.lab.id]

  user_data = <<-EOF
    #!/bin/bash
    yum update -y
    yum install -y python3 python3-pip
    echo "CloudForge lab instance ready" > /var/log/cloudforge-ready.log
  EOF

  tags = merge(var.tags, {
    Name = "${var.lab_name}-instance-${count.index}"
    Lab  = var.lab_name
  })
}

# ─── Outputs ──────────────────────────────────────────────────────────────────

output "instance_ids" {
  description = "IDs of the provisioned EC2 instances"
  value       = aws_instance.lab[*].id
}

output "public_ips" {
  description = "Public IP addresses of the instances"
  value       = aws_instance.lab[*].public_ip
}

output "public_ip" {
  description = "Public IP of the first instance"
  value       = length(aws_instance.lab) > 0 ? aws_instance.lab[0].public_ip : null
}

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.lab.id
}

output "region" {
  description = "AWS region"
  value       = var.region
}

output "lab_name" {
  description = "Lab name"
  value       = var.lab_name
}
