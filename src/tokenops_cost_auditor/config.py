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
    max_concurrent_audits: int = 2  # NFR-13 (R-API): admission cap, D6 consumer
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
