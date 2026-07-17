# deploy/ — one-command deployment (WP-DEPLOY-1, R-DEPLOY-AUTOMATION)

This directory is the seed of the R-MARKETPLACE IaC ladder (compose bundle →
Helm → marketplace templates). Everything here obeys R-DEPLOYMENT-CONTRACT:
single placeable artifact, zero required egress, bring-your-own
infrastructure, no phone-home.

## Path A — Hetzner, from a clean account

```bash
cd deploy/tf
terraform init
terraform apply \
  -var hcloud_token=... \
  -var domain=audit.example.com \
  -var git_tag=d13
```

Creates a CX32-class server (4 vCPU / 8 GB per runbook §1 — confirm the live
price in the Hetzner console at purchase; the public pricing page is
JS-rendered and was not machine-verifiable at build time), a 22/80/443
firewall, and your SSH key, then runs `scripts/provision.sh` against it.

## Path B — any existing Ubuntu host (BYO VM)

```bash
scripts/provision.sh --host <ip> --domain audit.example.com --tag d13
```

Same script Terraform calls — Hetzner is never required. With `--repo <url>`
the host clones that remote; without it, your local checkout's tag content
ships over ssh via `git archive` (works with no git remote at all).

Both paths end with the runbook §2 smoke checklist executed on the host and
the healthz JSON printed. Afterwards: point the DNS A record, verify
`https://<domain>/healthz` externally, run the VPS perf/memory re-validation,
append the CHANGELOG entry.

## What is deliberately absent

No CI auto-deploy. Per the recorded trigger (BACKLOG.md): auto-deploy-on-tag
is authorized only when >1 app ships from the monorepo (post WP-PLAT-0) or
deploy frequency exceeds 1/week for a month. Until then every deploy is
founder-initiated, one command, human-observed.
