"""NFR-15 (R-PRICING-OPS): warn — NEVER fail — when prices.yaml last_verified is
older than 14 days. CI prints a GitHub warning annotation; the daily digest (D10)
reuses age_days(). Exit code is always 0 by design."""

import datetime
import sys

from tokenops_cost_auditor.services.pricing.table import PricingTable

MAX_AGE_DAYS = 14


def age_days(table: PricingTable, today: datetime.date) -> int | None:
    if table.last_verified is None:
        return None
    return (today - table.last_verified).days


def main() -> int:
    table = PricingTable.load()
    age = age_days(table, datetime.date.today())
    if age is None:
        print("::warning title=Pricing table::prices.yaml has NO last_verified date (NFR-15)")
    elif age > MAX_AGE_DAYS:
        print(
            f"::warning title=Pricing table stale::prices.yaml last_verified is {age} days old "
            f"(> {MAX_AGE_DAYS}); re-verify against provider pricing pages (runbook section 8)"
        )
    else:
        print(f"pricing table age OK: last_verified {table.last_verified} ({age} days)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
