# Provider-variable clean (R-DEPLOY-AUTOMATION 1): Hetzner creation is
# optional — set create_server=false and existing_host_ip to deploy onto ANY
# Ubuntu host (bring-your-own VM, per R-DEPLOYMENT-CONTRACT clause 4).

variable "hcloud_token" {
  description = "Hetzner Cloud API token (unused when create_server=false)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "create_server" {
  description = "true: create a Hetzner server; false: use existing_host_ip"
  type        = bool
  default     = true
}

variable "existing_host_ip" {
  description = "IPv4 of an existing Ubuntu host (create_server=false path)"
  type        = string
  default     = ""
}

variable "server_type" {
  description = "Hetzner plan (runbook §1: CX32-class, 4 vCPU / 8 GB)"
  type        = string
  default     = "cx32"
}

variable "location" {
  type    = string
  default = "fsn1"
}

variable "image" {
  type    = string
  default = "ubuntu-24.04"
}

variable "ssh_public_key_path" {
  type    = string
  default = "~/.ssh/id_ed25519.pub"
}

variable "ssh_private_key_path" {
  type    = string
  default = "~/.ssh/id_ed25519"
}

variable "domain" {
  description = "Public domain for Caddy auto-TLS (DNS A record must point at the server)"
  type        = string
}

variable "git_tag" {
  description = "Repo tag to deploy (runbook §2: rollback = previous tag)"
  type        = string
  default     = "d13"
}

variable "repo_url" {
  description = "Git remote to clone; empty = ship the local checkout via git archive"
  type        = string
  default     = ""
}
