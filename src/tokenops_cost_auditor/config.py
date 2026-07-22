"""Application settings. Every environment variable is declared here (docs/03-LLD.md §7).

.env.example must list every field below in UPPER_CASE — enforced by
tests/test_smoke.py::test_env_example_complete.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Core
    app_env: str = "dev"  # dev | staging | prod
    secret_key: str = "dev-secret-change-me"  # 64B random in prod (runbook §5)
    database_url: str = (
        "postgresql+psycopg://tokenops_cost_auditor:tokenops_cost_auditor@localhost:5432/tokenops"
    )
    upload_dir: Path = Path("uploads")
    report_dir: Path = Path("reports")
    backup_dir: Path = Path("backups")  # digest freshness check (runbook §3); dumps land here
    max_upload_mb: int = 200  # FR-01
    max_concurrent_audits: int = 2  # NFR-13 (R-API): admission cap, D6 consumer
    purge_after_days: int = 7  # FR-21
    admin_token: str = ""  # empty = admin disabled

    # Payments (env-gated, FR-18) — payment links are static URLs; webhooks verified
    # with stdlib HMAC (PLAN.md §0.2 PAYMENT-SDKS).
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    # Signup federation (founder order 2026-07-27): Google OAuth sign-in.
    # Config-gated end to end — with no client id the button never renders,
    # because a dead button is a promise (R-GTM-CONTROL).
    # Public docs site. Absolute by default: the app itself never serves the
    # docs build, so a relative path 404s (walkthrough punch 2026-07-22 —
    # every Docs link on the product pointed at /docs-site/ and died).
    docs_url: str = "https://docs.tokenops-cost-auditor.com"
    # R-DOMAIN-MIGRATE (founder 2026-07-22): every outward-facing address is
    # config, so the tokenops-cost-auditor.com → tokenops-cost-auditor.com cutover is an
    # .env flip, not a code change. Defaults stay on the CURRENT live domain;
    # the cutover flips them (runbook §2b) once DNS resolves.
    support_email: str = "support@tokenops-cost-auditor.com"
    # Dead-button law: the footer Status link renders ONLY once this is set —
    # which happens when the UptimeRobot page + CNAME actually resolve
    # (runbook §3b step 5). An empty default keeps a dead link off every page.
    status_url: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    razorpay_webhook_secret: str = ""
    razorpay_payment_link_url: str = ""
    stripe_webhook_secret: str = ""
    stripe_payment_link_url: str = ""

    # Mail (env-gated, FR-20) — unset SMTP_HOST = log-only adapter
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    app_base_url: str = (
        ""  # absolute-link prefix for emails (FR-20), e.g. https://audit.example.com
    )
    digest_to: str = ""  # founder address for the daily ops digest; empty = stdout only

    # Observability (NFR-06, env-gated)
    sentry_dsn: str = ""

    # Detector thresholds (docs/03-LLD.md §3; money-math defaults recorded in the
    # golden spreadsheet notes sheet per founder ruling R-Q6..Q12).
    d1_short_completion_t: int = 150  # R-D1-MAP(d): LLD default, p50 boundary
    # R-D1-MAP (founder, 2026-07-17; sources = prices.yaml source_urls same date).
    # Frontier models WITHOUT a mapped downgrade -> informational finding, no
    # savings number (R-D1-MAP f). Extend this list for new frontier models before
    # their map entry is ruled.
    d1_frontier_models: list[str] = []
    # Downgrade map: exactly ONE tier down, never chained, never cross-provider
    # (R-D1-MAP a/b). Savings computed at the suggested model's four-rate card,
    # confidence=estimated (R-D1-MAP c). Longest-key prefix match on model id.
    d1_model_map: dict[str, str] = {
        # Anthropic (rates verified 2026-07-17)
        "claude-fable-5": "claude-opus-4-8",
        "claude-opus-4-8": "claude-sonnet-5",
        "claude-opus-4-7": "claude-sonnet-5",
        "claude-opus-4-6": "claude-sonnet-5",
        "claude-opus-4-1": "claude-opus-4-8",  # legacy uplift case
        "claude-opus-4-0": "claude-opus-4-8",  # legacy uplift case (alias id)
        "claude-opus-4": "claude-opus-4-8",  # legacy uplift (dated ids, boundary-safe)
        "claude-sonnet-5": "claude-haiku-4-5",
        "claude-sonnet-4-6": "claude-haiku-4-5",
        # OpenAI (rates verified 2026-07-17)
        "gpt-5.5-pro": "gpt-5.5",
        "gpt-5.4-pro": "gpt-5.5",
        "gpt-5.6-sol": "gpt-5.6-terra",
        "gpt-5.5": "gpt-5.6-terra",
        "gpt-5.6-terra": "gpt-5.6-luna",
        "gpt-5.4": "gpt-5.6-luna",
        "gpt-5.4-mini": "gpt-5.4-nano",
    }
    d2_cache_min_repeats: int = 25
    d2_cache_min_prompt_tokens: int = 1024
    d2_suffix_haircut: float = 0.8  # R-Q5: cacheable = 0.8 x min(prompt_tokens) w/o hash
    d2_ttl_window_s: int = 300  # R-Q4 fallback: one cache write per TTL window/prefix
    # Founder correction C4 (2026-07-17): TTL per provider-family, not global.
    # Keys match provider name or a model-id prefix; longest matching key wins;
    # unmatched traffic falls back to d2_ttl_window_s.
    d2_ttl_windows: dict[str, int] = {"anthropic": 300, "gpt-5.6": 1800}
    d2_no_window_haircut: float = 0.7  # R-Q4: haircut when windows cannot be estimated
    d3_bloat_mult: float = 2.0
    d4_window_s: int = 120
    d4_dup_min: int = 3
    d5_reserved_billing: bool = False
    d5_max_ratio: float = 4.0  # LLD: flag when declared_max >= 4x completion p95
    d6_loop_min: int = 8
    d6_batch_sz: int = 5
    d6_small_completion_t: int = 300  # LLD: loop calls are < 300 completion tokens
    d6_run_window_s: int = 600  # LLD: run of small calls within 10 min
    d6_session_gap_s: int = 900  # LLD: session = tag + 15-min gap split
    d6_reread_min: int = 5  # LLD: same prefix_hash >= 5 in session = agent re-read
    prefix_hash_chars: int = 4096  # R-Q6: SHA-256 over first N chars (~1024 tokens)
    rules_disabled: list[str] = []  # detector names to skip (T-RUL-00 disable flag)

    # Report & sessions (founder-accepted defaults Q9/Q11)
    report_url_expiry_days: int = 30
    session_ttl_days: int = 7

    # Display (NFR-11: USD internal; INR display via fixed configurable rate)
    inr_per_usd_display: float = 90.0

    # ---- v1.5 MONITOR (PLAN-V15 §0 rulings) ----
    # Plans (R-PRICING-FINAL-2, founder-ratified 2026-07-22): dual-market
    # structure — global USD via Stripe, India INR via Razorpay, prices ONLY
    # here, never inline. LIST prices below; LAUNCH prices apply per market
    # while its first-N cohort is open, and are kept for life provider-side
    # (a subscription charges what it started at). Launch 0 = no launch tier
    # for that plan (India Scale is flat). Supersedes R-Q11's both-currency
    # display: each viewer sees ONE currency, by billing country.
    plan_pro_usd: float = 29.0
    plan_team_usd: float = 99.0
    plan_pro_inr: float = 999.0
    plan_team_inr: float = 14999.0
    plan_pro_usd_launch: float = 19.0
    plan_team_usd_launch: float = 59.0
    plan_pro_inr_launch: float = 499.0
    plan_team_inr_launch: float = 0.0
    launch_cohort_size: int = 200  # per market; USD and INR count separately
    # Founder clarification 2026-07-22: SINGLE display currency (dollars)
    # everywhere; the REGION changes the value. India's dollar display points
    # below pair with the INR charge amounts above (₹499/₹999/₹14,999 billed
    # by Razorpay; the pairing is a price-point decision, not an FX formula —
    # R-PRICING-FINAL §2's "PPP set independently of FX").
    plan_pro_usd_india: float = 9.99
    plan_pro_usd_india_launch: float = 4.99
    plan_team_usd_india: float = 149.0
    one_shot_usd: float = 500.0
    one_shot_inr: float = 20000.0
    one_shot_usd_india: float = 199.0
    # Audited-spend gates (R-PRICING-FINAL §1): stated tier bounds and the
    # enterprise handoff line — copy, not metering.
    plan_pro_spend_gate_usd: float = 25000.0
    plan_team_spend_gate_usd: float = 100000.0
    # Honest qualifying threshold on pricing surfaces (§5 worth test)
    qualify_spend_usd: float = 500.0
    # R-Q5/Q6: a "source" = one active provider org connection
    # R-FREE-CONNECT (founder-ratified 2026-07-27): Free connects ONE source;
    # its single audit is metered by the signup comp credit, and the
    # scheduler never pulls free sources (entitlement filter).
    plan_source_limits: dict[str, int] = {"free": 1, "pro": 1, "team": 5}
    # Connect (T2): first-connect backfill window (accepted default Q2)
    connect_backfill_days: int = 30
    # Alerts (WP-3, observe-and-alert only; accepted defaults Q10 — see STATUS M1)
    alert_spend_spike_dod_pct: float = 30.0
    alert_waste_target_pct: float = 25.0
    # Dunning (R-Q12): day 7 read-only, day 21 cancelled -> Free
    dunning_readonly_days: int = 7
    dunning_cancel_days: int = 21


@lru_cache
def get_settings() -> Settings:
    return Settings()
