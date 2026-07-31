"""T-NFR-15: pricing-age checker warns (never fails) past 14 days."""

import datetime
import importlib.util
import sys
from pathlib import Path

import pytest

from tokenops_cost_auditor.services.pricing.table import PricingTable

SCRIPT = Path(__file__).parents[1] / "scripts" / "pricing_age.py"


def _load():
    spec = importlib.util.spec_from_file_location("pricing_age", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["pricing_age"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.verifies_requirement("NFR-15")
class TestTNFR15PricingAge:
    def test_fresh_table_ok_and_stale_warns_without_failing(self, capsys) -> None:
        mod = _load()
        table = PricingTable.load()
        assert table.last_verified is not None  # NFR-15 field present
        assert mod.age_days(table, table.last_verified) == 0
        assert mod.age_days(table, table.last_verified + datetime.timedelta(days=15)) == 15
        # main() must ALWAYS exit 0 — warning, never failure
        assert mod.main() == 0
        out = capsys.readouterr().out
        assert "pricing table" in out.lower()
