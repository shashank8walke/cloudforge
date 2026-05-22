terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

# ─── Variables ────────────────────────────────────────────────────────────────

variable "project" {
  description = "GCP project ID (not the display name — the unique project identifier)"
  type        = string
}

variable "region" {
  description = "GCP region to deploy resources into"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP zone for the compute instance (must be within var.region)"
  type        = string
  default     = "us-central1-a"
}

variable "project_name" {
  description = "Unique name for this CloudForge lab (used to name all resources)"
  type        = string
}

variable "machine_type" {
  description = "GCP machine type. f1-micro is the smallest available (legacy shared-core)."
  type        = string
  default     = "f1-micro"
}

variable "image" {
  description = "Boot disk image for the compute instance"
  type        = string
  default     = "debian-cloud/debian-12"
}

variable "tags" {
  description = "Key-value labels to apply to every resource (GCP calls these 'labels')"
  type        = map(string)
  default     = {}

  # GCP label keys/values must be lowercase letters, digits, underscores, or hyphens.
  # Enforce this in the calling LabSpec rather than here to keep the TF config simple.
}

# ─── Provider ─────────────────────────────────────────────────────────────────

provider "google" {
  project = var.project
  region  = var.region
  zone    = var.zone
}

# ─── Locals ───────────────────────────────────────────────────────────────────
# GCP uses "labels" (not "tags") — same concept, different API field name.
# Keys and values must be lowercase; use lower() to normalise project_name.

locals {
  common_labels = merge(
    var.tags,
    {
      project    = lower(var.project_name)
      managed_by = "cloudforge"
      provider   = "gcp"
    }
  )
}

# ─── Random suffix for globally-unique bucket name ────────────────────────────

resource "random_id" "bucket_suffix" {
  byte_length = 4

  keepers = {
    project_name = var.project_name
  }
}

# ─── Compute Instance ─────────────────────────────────────────────────────────

resource "google_compute_instance" "lab" {
  name         = "${lower(var.project_name)}-instance"
  machine_type = var.machine_type
  zone         = var.zone

  boot_disk {
    initialize_params {
      image = var.image
      # Increase from the default 10 GB to give the smoke tests room to work.
      size  = 20
      type  = "pd-standard"
    }
  }

  network_interface {
    # Attach to the project's default VPC.
    network = "default"

    # access_config with no fields requests an ephemeral public IP.
    access_config {}
  }

  metadata_startup_script = <<-EOF
    #!/bin/bash
    set -euo pipefail
    apt-get update -y
    apt-get install -y python3 python3-pip
    echo "cloudforge-ready" > /var/log/cloudforge-ready.log
  EOF

  labels = local.common_labels

  tags = ["cloudforge", lower(var.project_name)]
}

# ─── Cloud Storage Bucket ─────────────────────────────────────────────────────

resource "google_storage_bucket" "lab" {
  # GCS bucket names are globally unique across all GCP projects.
  name     = "${lower(var.project_name)}-${random_id.bucket_suffix.hex}"
  location = upper(var.region)   # GCS location must be uppercase, e.g. "US-CENTRAL1"

  # Prevent accidental deletion of non-empty buckets.
  force_destroy = false

  # Uniform bucket-level access disables per-object ACLs in favour of IAM,
  # which is the recommended modern approach.
  uniform_bucket_level_access = true

  labels = local.common_labels
}

# ─── Outputs ──────────────────────────────────────────────────────────────────

output "instance_name" {
  description = "GCP compute instance name"
  value       = google_compute_instance.lab.name
}

output "external_ip" {
  description = "Ephemeral external IP address assigned to the compute instance"
  value       = google_compute_instance.lab.network_interface[0].access_config[0].nat_ip
}

output "bucket_name" {
  description = "Name of the GCS artefact bucket"
  value       = google_storage_bucket.lab.name
}

output "project" {
  description = "GCP project the lab was deployed into"
  value       = var.project
}

output "region" {
  description = "GCP region the lab was deployed into"
  value       = var.region
}

output "project_name" {
  description = "Project name passed in at apply time"
  value       = var.project_name
}
