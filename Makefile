# Founder-facing shortcuts. Everything runs through the pinned toolchain (TE-11).
.PHONY: preview preview-empty preview-reset trace trace-ui test lint

## preview: seed a throwaway local account and open the v1.5 app with a magic link
preview:
	uv run python scripts/preview.py

## preview-empty: same, but an account with no data (first-run screens)
preview-empty:
	uv run python scripts/preview.py --empty --reset

## preview-reset: wipe .preview/ and start fresh
preview-reset:
	uv run python scripts/preview.py --reset

## trace: text summary of requirement -> test traceability (LE-9)
trace:
	uv run python scripts/trace.py status

## trace-ui: local traceability console in the browser (LE-9)
trace-ui:
	uv run python scripts/trace.py serve

test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check . && uv run mypy src/tokenops_cost_auditor/
