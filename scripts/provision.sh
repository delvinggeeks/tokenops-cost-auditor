#!/usr/bin/env bash
# WP-DEPLOY-1 (R-DEPLOY-AUTOMATION): one command from a clean Ubuntu host to
# serving TLS, executing runbook §2 steps 1-6 verbatim. Works on a Hetzner VM
# created by deploy/tf/ OR any generic Ubuntu 22.04/24.04 host you can ssh to
# as root with keys. Deploys are founder-initiated and human-observed (the CD
# trigger in BACKLOG.md is NOT authorized yet) — read the output.
#
# Usage:
#   scripts/provision.sh --host 1.2.3.4 --domain audit.example.com --tag d13 \
#       [--repo <git-url>] [--ssh-key ~/.ssh/id_ed25519] [--ssh-user root]
#
# With --repo the host clones that remote at --tag; without it, the LOCAL
# checkout's tag content ships via `git archive` over ssh (works for a repo
# with no remote). Secrets are generated ON the host on first run and kept
# across re-runs (.env is never overwritten once present).
set -euo pipefail

HOST="" DOMAIN="" TAG="" REPO="" SSH_KEY="$HOME/.ssh/id_ed25519" SSH_USER="root"
while [ $# -gt 0 ]; do
    case "$1" in
        --host) HOST="$2"; shift 2 ;;
        --domain) DOMAIN="$2"; shift 2 ;;
        --tag) TAG="$2"; shift 2 ;;
        --repo) REPO="$2"; shift 2 ;;
        --ssh-key) SSH_KEY="$2"; shift 2 ;;
        --ssh-user) SSH_USER="$2"; shift 2 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done
[ -n "$HOST" ] && [ -n "$DOMAIN" ] && [ -n "$TAG" ] || {
    echo "required: --host --domain --tag (see header)" >&2; exit 2; }

SSH=(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "$SSH_USER@$HOST")
APP_DIR=/opt/tokenops-cost-auditor

echo "== [1/6] wait for ssh =="
for i in $(seq 1 30); do "${SSH[@]}" true 2>/dev/null && break; sleep 5; done
"${SSH[@]}" true

echo "== [2/6] harden (runbook §2 step 1: ufw 22/80/443, fail2ban, keys-only) =="
"${SSH[@]}" bash -s <<'HARDEN'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ufw fail2ban git rsync >/dev/null
ufw allow 22/tcp >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl reload ssh 2>/dev/null || systemctl reload sshd
systemctl enable --now fail2ban >/dev/null
echo "hardened: ufw active, password auth off, fail2ban up"
HARDEN

echo "== [3/6] docker (runbook §2 step 2) =="
"${SSH[@]}" bash -s <<'DOCKER'
set -euo pipefail
if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sh >/dev/null
fi
docker compose version >/dev/null
echo "docker ready: $(docker --version)"
DOCKER

echo "== [4/6] ship code at tag $TAG (runbook §2 step 3) =="
if [ -n "$REPO" ]; then
    "${SSH[@]}" bash -s <<CLONE
set -euo pipefail
if [ -d "$APP_DIR/.git" ]; then
    cd "$APP_DIR" && git fetch --tags -q && git checkout -q "$TAG"
else
    git clone -q --branch "$TAG" --depth 1 "$REPO" "$APP_DIR"
fi
CLONE
else
    # no remote: ship the local checkout's tag content exactly (git archive)
    "${SSH[@]}" "mkdir -p $APP_DIR"
    git -C "$(dirname "$0")/.." archive "$TAG" | "${SSH[@]}" "tar -x -C $APP_DIR"
fi

echo "== [4b] .env from template (secrets generated on host, kept across runs) =="
"${SSH[@]}" bash -s <<ENVSETUP
set -euo pipefail
cd "$APP_DIR"
if [ ! -f .env ]; then
    sed -e "s|^SECRET_KEY=.*|SECRET_KEY=\$(openssl rand -hex 64)|" \
        -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=\$(openssl rand -hex 24)|" \
        -e "s|^ADMIN_TOKEN=.*|ADMIN_TOKEN=\$(openssl rand -hex 32)|" \
        -e "s|^APP_ENV=.*|APP_ENV=prod|" \
        -e "s|^DOMAIN=.*|DOMAIN=$DOMAIN|" \
        -e "s|^APP_BASE_URL=.*|APP_BASE_URL=https://$DOMAIN|" \
        .env.example > .env
    chmod 600 .env
    echo ".env created (chmod 600). SMTP_* left empty — mail uses the log adapter until filled."
else
    echo ".env exists — kept (secrets never regenerated)"
fi
ENVSETUP

echo "== [4c] docs-site: build locally, ship to host (docs.$DOMAIN) =="
if command -v uv >/dev/null 2>&1 && [ -f "$(dirname "$0")/../mkdocs.yml" ]; then
    (cd "$(dirname "$0")/.." && uv run mkdocs build -q)
    rsync -az --delete -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new" \
        "$(dirname "$0")/../site/" "$SSH_USER@$HOST:$APP_DIR/site/"
    echo "docs-site shipped to $APP_DIR/site"
else
    echo "WARNING: uv or mkdocs.yml missing on deploy machine — docs.$DOMAIN will 404"
fi

echo "== [5/6] compose up + migrations (runbook §2 steps 4-5) =="
"${SSH[@]}" bash -s <<UP
set -euo pipefail
cd "$APP_DIR"
docker compose up -d --build
for i in \$(seq 1 40); do
    docker compose ps app --format '{{.Status}}' | grep -q healthy && break; sleep 5
done
docker compose exec -T app alembic upgrade head
UP

echo "== [6/6] smoke checklist (runbook §2 step 6) =="
"${SSH[@]}" bash -s <<SMOKE
set -euo pipefail
cd "$APP_DIR"
echo "- healthz:"
# SNI must match a configured site: probe the real domain resolved to loopback
# (plain https://localhost has no site block once DOMAIN is a real hostname).
curl -sk --resolve "$DOMAIN:443:127.0.0.1" "https://$DOMAIN/healthz"; echo
curl -sk --resolve "$DOMAIN:443:127.0.0.1" "https://$DOMAIN/" | grep -q "Take control of your AI spend." \
    && echo "- landing: OK (control narrative served)"
curl -sk --resolve "$DOMAIN:443:127.0.0.1" -X POST "https://$DOMAIN/auth/magic-link" -d "email=deploy-smoke@example.com" -o /dev/null -w "- magic-link request: %{http_code}\n"
sleep 1
docker compose logs app 2>&1 | grep -q "/auth/verify?token=" \
    && echo "- magic link issued (log adapter; arrives by email once SMTP_* is set)"
docker compose logs ofelia 2>&1 | grep -c "New job registered" | xargs -I{} echo "- ofelia jobs registered: {}"
curl -sk --resolve "docs.$DOMAIN:443:127.0.0.1" "https://docs.$DOMAIN/" -o /dev/null -w "- docs-site: %{http_code}\n"
curl -sk --resolve "www.$DOMAIN:443:127.0.0.1" "https://www.$DOMAIN/" -o /dev/null -w "- www redirect: %{http_code}\n"
SMOKE

echo
echo "DONE. Point DNS A record for $DOMAIN at $HOST — Caddy fetches TLS on"
echo "first request. Then verify https://$DOMAIN/healthz from outside, run the"
echo "VPS perf/memory re-validation (R-SEQ-POST-SIGNOFF), and record the deploy"
echo "in CHANGELOG.md (runbook §2 step 7)."
