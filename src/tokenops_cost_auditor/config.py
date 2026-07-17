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
    max_upload_mb: int = 200  # FR-01
    purge_after_days: int = 7  # FR-21
    admin_token: str = ""  # empty = admin disabled

    # Payments (env-gated, FR-18) — payment links are static URLs; webhooks verified
    # with stdlib HMAC (PLAN.md §0.2 PAYMENT-SDKS).
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
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

    # Observability (NFR-06, env-gated)
    sentry_dsn: str = ""

    # Detector thresholds (docs/03-LLD.md §3; money-math defaults recorded in the
    # golden spreadsheet notes sheet per founder ruling R-Q6..Q12).
    d1_short_completion_t: int = 150
    d1_frontier_models: list[str] = []  # seeded at D5 with founder-verified list
    d1_model_map: dict[str, str] = {}  # frontier -> suggested cheaper model, D5
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
    d6_loop_min: int = 8
    d6_batch_sz: int = 5
    prefix_hash_chars: int = 4096  # R-Q6: SHA-256 over first N chars (~1024 tokens)

    # Report & sessions (founder-accepted defaults Q9/Q11)
    report_url_expiry_days: int = 30
    session_ttl_days: int = 7

    # Display (NFR-11: USD internal; INR display via fixed configurable rate)
    inr_per_usd_display: float = 90.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
