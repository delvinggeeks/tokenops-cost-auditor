# WP-DEPLOY-1: infrastructure creation only — ALL host configuration lives in
# scripts/provision.sh so the Terraform path and the bare
# "./scripts/provision.sh --host <ip>" path are the SAME code.

resource "hcloud_ssh_key" "operator" {
  count      = var.create_server ? 1 : 0
  name       = "tokenops-operator"
  public_key = file(pathexpand(var.ssh_public_key_path))
}

resource "hcloud_firewall" "web" {
  count = var.create_server ? 1 : 0
  name  = "tokenops-web"
  dynamic "rule" {
    for_each = [22, 80, 443]
    content {
      direction  = "in"
      protocol   = "tcp"
      port       = tostring(rule.value)
      source_ips = ["0.0.0.0/0", "::/0"]
    }
  }
}

resource "hcloud_server" "app" {
  count        = var.create_server ? 1 : 0
  name         = "tokenops-cost-auditor"
  server_type  = var.server_type
  location     = var.location
  image        = var.image
  ssh_keys     = [hcloud_ssh_key.operator[0].id]
  firewall_ids = [hcloud_firewall.web[0].id]
}

locals {
  target_ip = var.create_server ? hcloud_server.app[0].ipv4_address : var.existing_host_ip
}

resource "terraform_data" "provision" {
  triggers_replace = [local.target_ip, var.git_tag]

  provisioner "local-exec" {
    command = join(" ", [
      "${path.module}/../../scripts/provision.sh",
      "--host", local.target_ip,
      "--domain", var.domain,
      "--tag", var.git_tag,
      var.repo_url == "" ? "" : "--repo ${var.repo_url}",
      "--ssh-key", pathexpand(var.ssh_private_key_path),
    ])
  }
}
