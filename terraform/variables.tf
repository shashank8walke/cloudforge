# =============================================================================
# terraform/variables.tf — Shared variable definitions
# =============================================================================
# This file is the canonical reference for every variable used across the
# CloudForge Terraform modules (terraform/aws/ and terraform/gcp/).
#
# HOW TO USE
# ----------
# Terraform treats each sub-directory as an independent root module.  Variables
# cannot be shared across directories by file inclusion.  Instead, this file
# documents the full contract so that:
#   • both modules use identical names, types, and descriptions;
#   • callers (CloudForge provisioner.py) pass a consistent set of values;
#   • future modules (Azure, etc.) have a single reference to follow.
#
# Each module (aws/main.tf, gcp/main.tf) declares only the variables it needs,
# but the names and types here are authoritative.
# =============================================================================

# ─── Universal ────────────────────────────────────────────────────────────────

variable "project_name" {
  description = <<-EOT
    Unique, human-readable name for this CloudForge lab.
    Used as a prefix for every resource name so resources from different labs
    never collide.  Must be lowercase, alphanumeric, and hyphen-only to satisfy
    both AWS and GCP naming constraints.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$", var.project_name))
    error_message = "project_name must be 3-32 chars, lowercase letters, digits, and hyphens only."
  }
}

variable "region" {
  description = <<-EOT
    Deployment region.
    AWS example  : "us-east-1"
    GCP example  : "us-central1"
    Defaults differ per provider — each module sets its own default.
  EOT
  type    = string
  default = "us-east-1"
}

variable "tags" {
  description = <<-EOT
    Arbitrary key-value metadata applied to every resource.
    AWS calls these "tags"; GCP calls them "labels".  CloudForge merges these
    with the standard ManagedBy / Provider / Project tags in locals.common_tags
    (AWS) or locals.common_labels (GCP).

    GCP label keys and values must be lowercase letters, digits, hyphens, or
    underscores and no longer than 63 characters.
  EOT
  type    = map(string)
  default = {}
}

# ─── AWS-specific ─────────────────────────────────────────────────────────────

variable "instance_type" {
  description = <<-EOT
    EC2 instance type for the lab server.
    t2.micro is free-tier eligible and sufficient for smoke tests.
    Must be available in the target region.
  EOT
  type    = string
  default = "t2.micro"
}

variable "ami_id" {
  description = <<-EOT
    Amazon Machine Image ID used to launch the EC2 instance.
    Default: Amazon Linux 2 in us-east-1 (ami-0c02fb55956c7d316).
    Override when deploying into a different region — AMI IDs are region-scoped.
  EOT
  type    = string
  default = "ami-0c02fb55956c7d316"
}

# ─── GCP-specific ─────────────────────────────────────────────────────────────

variable "project" {
  description = <<-EOT
    GCP project ID (the unique identifier, not the display name).
    Found in the GCP console under "Project info" or via:
      gcloud projects list --format="value(projectId)"
  EOT
  type = string
  # No default — must be explicitly provided for GCP deployments.
}

variable "zone" {
  description = <<-EOT
    GCP zone for the compute instance.  Must be within var.region.
    Example: if region = "us-central1", valid zones are
    "us-central1-a", "us-central1-b", "us-central1-c", "us-central1-f".
  EOT
  type    = string
  default = "us-central1-a"
}

variable "machine_type" {
  description = <<-EOT
    GCP machine type for the compute instance.
    f1-micro is the smallest available (legacy shared-core, 0.2 vCPU, 0.6 GB RAM).
    e2-micro is the recommended free-tier equivalent on modern hardware.
  EOT
  type    = string
  default = "f1-micro"
}

variable "image" {
  description = <<-EOT
    Boot disk image for the GCP compute instance.
    Format: "<project>/<family>" or "<project>/<image-name>"
    Defaults to the latest Debian 12 (Bookworm) image.
  EOT
  type    = string
  default = "debian-cloud/debian-12"
}
