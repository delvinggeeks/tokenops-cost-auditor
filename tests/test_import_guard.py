"""T-NFR-01 import guard (NFR-01, CLAUDE.md rule 2): services/rules and
services/pricing import zero network/LLM libraries. Static AST check — the
engine must be deterministic by construction."""

import ast
from pathlib import Path

SRC = Path(__file__).parents[1] / "src" / "tokenops_cost_auditor" / "services"
GUARDED_PACKAGES = ("rules", "pricing")
# Single deterministic modules held to the same law (vv-gate 01334e8 f.4: the
# forecast was clean by discipline only — enforcement belongs here).
GUARDED_MODULES = ("forecast.py",)
FORBIDDEN = {
    "anthropic",
    "openai",
    "httpx",
    "requests",
    "aiohttp",
    "urllib3",
    "urllib",
    "socket",
    "http",
    "websockets",
    "grpc",
    "litellm",
}


def iter_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


class TestTNFR01ImportGuard:
    def test_no_network_or_llm_imports_in_engine(self) -> None:
        offenders: list[str] = []
        checked = 0
        for pkg in GUARDED_PACKAGES:
            for path in sorted((SRC / pkg).rglob("*.py")):
                checked += 1
                bad = iter_imports(path) & FORBIDDEN
                if bad:
                    offenders.append(f"{path}: {sorted(bad)}")
        for name in GUARDED_MODULES:
            path = SRC / name
            assert path.exists(), f"guarded module vanished: {path}"
            checked += 1
            bad = iter_imports(path) & FORBIDDEN
            if bad:
                offenders.append(f"{path}: {sorted(bad)}")
        assert checked >= 10, "guard must actually scan the engine modules"
        assert not offenders, "NFR-01 violated:\n" + "\n".join(offenders)

    def test_guard_detects_violations(self, tmp_path: Path) -> None:
        """The guard itself must not be a no-op."""
        bad = tmp_path / "bad.py"
        bad.write_text("import httpx\nfrom openai import OpenAI\n")
        assert iter_imports(bad) & FORBIDDEN == {"httpx", "openai"}
