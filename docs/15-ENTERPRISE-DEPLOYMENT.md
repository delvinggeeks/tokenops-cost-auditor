# docs/15 — Enterprise Deployment & Zero-Touch CI/CD (R-ENT-DEPLOY, founder 2026-07-28)

**DESIGN DOCUMENT ONLY.** Nothing here authorizes code. Every gap carries a TRIGGER, never
a date. The zero-egress law and no-phone-home constraint (R-DEPLOYMENT-CONTRACT clauses
2–3, `docs/internal/BACKLOG.md:129`) bind every customer-side path in this document.
Reconciled 2026-07-28 against what exists — file paths and ruling IDs cited throughout;
nothing already ruled is redesigned here. Slices: §8; formal requirements: docs/01 §I
(FR-39..42), per R-REQ-PIPELINE (docs/09 §9).

## 0. What exists today (the reconciliation base)

| Artifact | Path | What it is |
|---|---|---|
| Compose stack | `docker-compose.yml` | the single deployable artifact, v1 rung of the R-MARKETPLACE ladder |
| Provisioning | `scripts/provision.sh` | box preparation |
| IaC seed | `deploy/tf/` (+ `deploy/README.md`) | Terraform, Hetzner CX32 path; explicitly "the seed of the R-MARKETPLACE IaC ladder" |
| Deploy pipeline | `.github/workflows/deploy.yml` | SSH-based; staging auto-deploys on merge (LE-2), prod is founder-gated `workflow_dispatch` promotion |
| Local CLI | `src/tokenops_cost_auditor/cli.py` (`tokenops-cost-auditor audit\|ship\|link\|mcp`) | in-perimeter audit — log file in, report out, nothing leaves |
| Migration law | `docs/06-OPS-RUNBOOK.md:35` | additive-only in v1 (policy) — no down-migration risk |
| Backup law | `docs/06-OPS-RUNBOOK.md` §4 | NFR-08 backup & restore procedure |
| Governing rulings | R-DEPLOYMENT-CONTRACT (6 clauses), R-MARKETPLACE a (ladder) + b (user model), R-DEPLOY-AUTOMATION 2 (trigger), R-ZTA (docs/12) | all recorded in `docs/internal/BACKLOG.md` trigger register + docs/12 |
| Measured perf | `docs-site/engineering/performance.md` | see §3 — with the staleness caveat stated there |

## 1. Customer deployment modes

| Mode | Status | Gap to close (trigger, never a date) |
|---|---|---|
| **a. In-perimeter CLI** | ✅ SHIPPED | none. `tokenops-cost-auditor audit` runs the full deterministic engine locally; counts-only by construction (FR-22); nothing leaves the network — the strongest data-privacy answer we have |
| **b. Hosted SaaS** | ✅ SHIPPED | none. tokenops.cloud; staging+prod live (LE-2); counts/metadata only ever stored (FR-22) |
| **c. Customer-VPC self-hosted** | ◐ compose bundle exists (`docker-compose.yml` + `deploy/README.md` path B); BYO postgres/TLS/identity honored | **Helm chart** — T-E1 ← first VPC/self-hosted customer (R-MARKETPLACE a, BACKLOG:45) |
| **d. Air-gapped / offline bundle** | 📋 contract clause 5 requires it; nothing built | **bundle builder** (images.tar + checksums + offline license) — T-E2 ← first air-gapped deal |
| **e. Marketplace one-click** | 📋 `deploy/tf` is the named seed; no listings, no ARM/CFN/GCP-DM templates | **IaC templates + listings** — T-E3 ← first marketplace-sourced lead (BACKLOG:56) |

All five run the SAME artifact — one app image + compose/chart wrapping it; differences
are config-only (R-DEPLOYMENT-CONTRACT clause 1). No mode gains features another lacks.

## 2. Zero-touch CI/CD — two lanes, never conflated

### Lane A — OUR release train (tag → prod, no human hands)

Today, honestly: merge → staging auto-deploy (LE-2, SSH+compose via `deploy.yml`) →
founder reviews rendered pages → founder clicks `workflow_dispatch` promotion. That last
click is the design's deliberate human gate (SDLC memory: prod is FOUNDER-GATED), and it
stays until the recorded trigger fires.

Target train: `tag vX.Y.Z` → build image → gate-round green → deploy staging → smoke
(healthz + journey subset) → promote prod → post-cutover health gate → auto-rollback on
fail. Missing pieces vs today, each named with cost/egress implications:

| Piece | Today | Design | New dependency? |
|---|---|---|---|
| Image registry | none — box pulls git + compose build | GHCR (`ghcr.io/witaura/tokenops:<semver>`) | GHCR: $0 at our scale, egress only between GitHub and OUR boxes — customers unaffected (Lane A is our infra) |
| Image signing | none | cosign keyless (Sigstore) at publish; verify at deploy | cosign OSS, $0; verification is a local op |
| Promotion gate | founder click | smoke suite green on staging = the gate; founder click REPLACED only when the trigger below fires | none |
| Rollback trigger | manual | 3 consecutive `/healthz` fails OR smoke fail post-cutover → redeploy previous tag automatically | none |
| Rollback procedure | re-run deploy at old ref (manual) | redeploy image N-1; DB untouched — additive-only law (`06-OPS §2`) makes old-app-on-new-schema safe | none |
| Migration safety | additive-only law + §4 backups | codify order: backup (§4) → migrate → deploy → health gate; abort chain on any step | none |

**Authorization trigger (existing rule, verbatim R-DEPLOY-AUTOMATION 2, BACKLOG:60):**
(a) more than one app ships from the monorepo, OR (b) deploy frequency exceeds 1/week
for a month. Until then the founder-gated promotion stands — it is not a gap, it is law.

### Lane B — THEIR update path (self-hosted, zero-egress)

Constraint first: **no phone-home, ever** (contract clause 2). We never push, ping,
or update-check. The customer PULLS on their schedule; an air-gapped customer carries
a bundle across the gap. Telemetry is opt-in only and off by default.

| Element | Design |
|---|---|
| Versioned channel | signed images at `ghcr.io/witaura/tokenops` (public-pull), semver tags only, no `latest`; sha256 manifest published per release |
| Helm values contract | §7.2 — the STABLE surface; a value present in N works in N+1 (deprecate one minor ahead, never break) |
| Migration runner | pre-upgrade Job/init-container: backup-precondition documented → `alembic upgrade head` → app starts; additive-only law means the running N-1 app is never broken mid-upgrade |
| Offline bundle path | download bundle (§7.3) on a connected host → verify checksums + cosign sig → carry across gap → load images → `helm upgrade` (or compose re-tag). Same artifacts, no network semantics |
| Rollback | `helm rollback` / compose re-tag to N-1; DB stays at N schema — safe by the additive-only law; documented, tested per release (T-E5 acceptance) |
| **N-1 policy** | every release upgrades FROM the previous minor and rolls BACK to it; schema produced by N is readable by N-1 app. Skipping versions = step through each minor. Support window: N and N-1 |

## 3. Scale story — measured numbers ONLY

From `docs-site/engineering/performance.md` (source figures, with their caveats):

| Measured | Figure |
|---|---|
| 250k-class pack, full pipeline | 94.3 s total (ingest 8.5 s · price 1.2 s · detect 82.8 s · render 1.9 s), 1,771 MB peak RSS |
| 1M rows, single audit | 624 s (bound: 660 s, amended), 2.25 GiB app container |
| 2 × 1.3M rows concurrent | 34 m 20 s both complete; 5.14 GiB app + 150 MiB Postgres of 7.8 GiB |
| Concurrency cap | `MAX_CONCURRENT_AUDITS=2` (NFR-13); beyond cap = honest queued status with position |

**Honesty caveats, stated plainly:** the detect figure is from the SIX-detector era —
nine detectors now ship (d1–d6, d8–d10) and the full pack has NOT been re-timed; the
measuring machine is a 24-thread workstation the perf page itself calls faster than the
4-vCPU prod VPS; prod-box 1M-row timing is therefore DERIVED from bounds, not measured.
Not load-tested at all: >2 concurrent audits, read-API under load, multi-GB Postgres,
any multi-instance topology (never run), queue+workers (unbuilt).

**Scaling dimensions that matter** (user-model principle, R-MARKETPLACE b): data volume
and audit concurrency — later, policy-decision throughput (Phase 2). NOT concurrent
logins: employees are data sources, never platform users; ~5–50 reader seats per
enterprise regardless of headcount.

**Rungs, each with its trigger:**
1. **Bigger box** (config-only, exists today) ← sustained NFR-04 misses or memory >70%
   at cap-2 on the current class
2. **Queue + workers** (replaces BackgroundTasks + NFR-13 cap) ← trigger already
   recorded at BACKLOG:38 — no redesign here
3. **Multi-instance + external Postgres** ← single-box ceiling reached AFTER workers,
   or an enterprise deal requiring HA. NOT designed beyond this sentence until then.

## 4. Enterprise readiness ledger

Cross-links: `docs/internal/LIFECYCLE-MAP.md` (the ruling's "docs/13-LIFECYCLE-MAP"
reconciled to the actual path — docs/13 is the T4 OTLP spec).

| Capability | Status | Trigger | Effort | Evidence when done |
|---|---|---|---|---|
| SSO (readers) | 📋 designed (R-IAM; MAP row "SSO·SCIM·IAM") | O-3: first team customer | M | Entra login journey test green |
| SCIM | 📋 registered (R-IAM) | first SCIM-requiring deal | M | provision/deprovision round-trip test |
| SOC 2 | 📋 registered (BACKLOG:44) | enterprise procurement blocker | L | report from auditor; controls mapped to append-only log |
| DPA template | ❓ no recorded home — founder-lane legal artifact | first enterprise security review | S | signed template in repo `docs/legal/` |
| Security questionnaire pack | 📋 (R-ENTERPRISE-READY register, BACKLOG:24) | first security review | S | answered CAIQ-style doc citing FR-22/NFR-01/append-only |
| Helm chart | 📋 T-E1 | first VPC customer | M | `helm install` on kind → journey smoke green |
| Marketplace listings + IaC | 📋 T-E3 (`deploy/tf` is the seed) | first marketplace-sourced lead | L | one-click deploy from listing → healthz |
| Air-gap bundle | 📋 T-E2 (contract clause 5) | first air-gapped deal | M | offline install on a no-network VM → journey smoke |
| SLA / status page | ◐ UptimeRobot + CNAME founder-lane (ROADMAP §4; footer link must resolve pre-launch) | launch | S | status URL resolves; SLA doc published |
| Data export | ◐ report JSON/PDF + explorer (FR-32) shipped; full workspace export = gap | first DPA/offboarding request | S | export → reimport round-trip test |

## 5. THE ANSWER SHEET (read aloud on the enterprise call)

**"What leaves our network?"** — In CLI mode: nothing. The audit runs inside your
perimeter (`tokenops-cost-auditor audit`, shipped today) and the engine is incapable of
reading prompt text — it stores counts, hashes and metadata only (FR-22, enforced by
test). In SaaS mode: token counts and cost metadata, never prompt or completion text —
the schema has no column for it. Self-hosted: zero required egress; no phone-home; you
pull updates, we never push (R-DEPLOYMENT-CONTRACT clauses 2–3).

**"How does it run in our environment?"** — One artifact: the compose stack running
today on our own production (`docker-compose.yml`), placeable by your platform team;
bring your own Postgres, TLS, identity and storage (clause 4). Helm and marketplace
one-click are trigger-registered rungs of a recorded ladder (R-MARKETPLACE a) — the
Terraform seed exists in-repo (`deploy/tf/`). Air-gapped delivery is contract clause 5.

**"How does it scale?"** — Measured: one million call records audited in 624 seconds
inside 2.25 GiB on a single box; two concurrent 1.3M-row audits complete in 34 minutes
in under 5.2 GiB. Your scaling dimension is data volume, not user count — employees are
data sources; the platform serves ~5–50 readers regardless of headcount. Rungs beyond
the single box (queue+workers, multi-instance) are designed with named triggers.

**"How do we trust the numbers?"** — The engine is deterministic and LLM-free (NFR-01,
import-guarded by test); every rate is machine-verified against an independent source
before release (R-AUTO-PRICING, `scripts/pricing_verify.py`); the audit log is
INSERT-only at the DB-grant level (FR-21); our own spend is audited by the product and
published (32.5%, self-audit ledger, CI-gated).

## 6. HLD — one artifact, three channels

```
                    ┌── (a) CLI wheel/pipx ── runs IN perimeter, no server
  one app image ────┼── (b) our compose stack ── SaaS (staging/prod, LE-2)
  (same code, ──────┼── (c) compose bundle / Helm chart ── customer VPC
   config-only ─────┼── (d) offline bundle = (c) + images.tar + checksums
   differences)     └── (e) marketplace IaC wrapping (c)
```
Boundary law: the engine (`services/rules`, `services/pricing`) is identical bytes in
every channel — deployment NEVER forks behavior (clause 1 + determinism). Tenancy,
TLS, identity, storage are injected at the edge (clause 4, R-ORG boundary).

## 7. LLD contracts (bind future slices; expand at each slice's design gate)

**7.1 Image channel** — `ghcr.io/witaura/tokenops:<MAJOR.MINOR.PATCH>`; no `latest`;
cosign keyless signature + sha256 manifest per release; release notes state
`upgrades_from: [N-1 minors]`.

**7.2 Helm values (stable surface, N→N+1 compatible):**
```yaml
image: {repository, tag}            # pinned semver, never latest
postgres: {external: {host, port, database, existingSecret}}   # BYO (clause 4)
tls: {secretName}                   # BYO
ingress: {host, className}
resources: {requests, limits}
audit: {maxConcurrent: 2}           # NFR-13 knob
telemetry: {enabled: false}         # opt-in ONLY (clause 2); no other network toggles exist
```

**7.3 Offline bundle manifest (`bundle.json`):**
`{version, images: [{name, tag, sha256}], chart: {name, version, sha256}, upgrades_from: [...], signature}`
— verified before load; bundle contains everything; installer makes zero network calls.

**7.4 Migration runner** — pre-upgrade Job: assert backup precondition (documented, §4
runbook) → `alembic upgrade head` → exit 0 gates app rollout. Additive-only (06-OPS §2)
is the invariant that makes N-1 rollback safe; any future breaking migration requires a
founder ruling amending that law FIRST.

**7.5 Lane-A rollback** — post-cutover: 3 consecutive healthz fails or smoke fail →
redeploy previous tag (image is immutable in registry); DB untouched; alert the founder;
the failed tag is quarantined until a fix tag ships.

## 8. Vertical slices (SMART; ALL trigger-gated → QUEUE PARKED; zero build now)

- **T-E1 · FR-39** Helm chart (mode c gap) ← first VPC/self-hosted customer ·
  evidence: `helm install` on kind + journey smoke; values per §7.2
- **T-E2 · FR-39** air-gap bundle builder (mode d) ← first air-gapped deal ·
  evidence: offline install on no-network VM per §7.3
- **T-E3 · FR-39** marketplace IaC + listings (mode e; `deploy/tf` seed) ← first
  marketplace-sourced lead · evidence: one-click from listing → healthz
- **T-E4 · FR-40** Lane-A release train (registry+signing, smoke-gated promote,
  auto-rollback §7.5) ← R-DEPLOY-AUTOMATION 2 trigger, verbatim · evidence: a tag
  reaches prod with zero human steps in a drill
- **T-E5 · FR-41** Lane-B update channel (publish signed images, N-1 upgrade+rollback
  test matrix, migration runner §7.4) ← rides T-E1 (first Helm customer) · evidence:
  N-1→N→rollback cycle green in CI against kind
- Scale rungs (FR-42) are NOT slices here: rung 2 is already registered (BACKLOG:38);
  rung 3 is deliberately undesigned until its trigger (§3) — listing it as a slice
  would violate the trigger law.

— end. This document authorizes no code (R-ENT-DEPLOY rule); the slices above become
buildable only when their triggers fire and the founder sequences them into QUEUE NOW.
