output "server_ip" {
  value = local.target_ip
}

output "healthz_url" {
  value = "https://${var.domain}/healthz"
}

output "next_steps" {
  value = "Point the DNS A record for ${var.domain} at ${local.target_ip}; Caddy obtains TLS on first request. Record the deploy in CHANGELOG.md (runbook §2 step 7)."
}
