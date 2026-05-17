terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# ─── Variables ────────────────────────────────────────────────────────────────

variable "lab_name" {
  description = "Unique identifier for this test lab"
  type        = string
}

variable "project" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP zone"
  type        = string
  default     = "us-central1-a"
}

variable "machine_type" {
  description = "GCP machine type"
  type        = string
  default     = "e2-micro"
}

variable "instance_count" {
  description = "Number of lab instances"
  type        = number
  default     = 1
}

variable "image" {
  description = "Boot disk image"
  type        = string
  default     = "debian-cloud/debian-12"
}

variable "tags" {
  description = "Labels to apply to all resources"
  type        = map(string)
  default     = {}
}

# ─── Provider (stub — Phase 2) ────────────────────────────────────────────────

# NOTE: GCP provisioning is stubbed in Phase 1.
# Uncomment the provider block and resources when GCPProvisioner is implemented.

# provider "google" {
#   project = var.project
#   region  = var.region
#   zone    = var.zone
# }

# resource "google_compute_network" "lab" {
#   name                    = "${var.lab_name}-network"
#   auto_create_subnetworks = false
# }

# resource "google_compute_subnetwork" "lab" {
#   name          = "${var.lab_name}-subnet"
#   ip_cidr_range = "10.1.0.0/24"
#   region        = var.region
#   network       = google_compute_network.lab.id
# }

# resource "google_compute_instance" "lab" {
#   count        = var.instance_count
#   name         = "${var.lab_name}-vm-${count.index}"
#   machine_type = var.machine_type
#   zone         = var.zone
#
#   boot_disk {
#     initialize_params { image = var.image }
#   }
#
#   network_interface {
#     network    = google_compute_network.lab.id
#     subnetwork = google_compute_subnetwork.lab.id
#     access_config {}  # Assigns ephemeral public IP
#   }
#
#   labels = merge(var.tags, { lab = var.lab_name, managed_by = "cloudforge" })
# }

# output "instance_names" { value = google_compute_instance.lab[*].name }
# output "external_ips"   { value = google_compute_instance.lab[*].network_interface[0].access_config[0].nat_ip }

output "stub_notice" {
  value = "GCP provisioner is a stub — implement GCPProvisioner in cloudforge/provisioner.py (Phase 2)"
}
