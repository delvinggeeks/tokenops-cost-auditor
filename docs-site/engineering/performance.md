# Performance

## The target

The specified requirement: a 1-million-row JSONL export processes in under 10
minutes on a single 4-vCPU VPS. That is the machine class the product actually
runs on — not a benchmark rig. <!-- src: NFR-04, target as specified -->

## Measured run (T-PERF-01, 2026-07-17)

One million rows of mixed synthetic traffic (the seeded F7 fixture, waste
planted for all six detectors, 17,264 findings produced) through the full
pipeline — ingest, price, detect, assemble, render JSON:
<!-- src: MP-6 resolved per founder ruling R-PERF-MANUAL; uv run pytest tests/test_perf.py -m perf, 2026-07-17 -->

| Stage | Wall-clock |
|---|---|
| ingest + normalize | 8.5 s |
| price + reconcile (±0.5% property held at scale) | 1.2 s |
| detect (all six detectors) | 82.8 s |
| assemble + render JSON | 1.9 s |
| **Total** | **94.3 s** (bound: 600 s) |

Peak memory: 1,771 MB RSS. Machine: AMD Ryzen AI MAX+ 392 (24 threads),
27 GB RAM, Ubuntu 24.04, Python 3.14 — a development workstation, stated
plainly: it is faster than the 4-vCPU production VPS the NFR-04 target names.
The pipeline is effectively single-core (pandas), so the headroom is large
(6.4× under the bound), but the target will be re-verified on production
hardware at deploy and this table updated with that run.

## Determinism (measured today)

The same upload produces byte-identical findings JSON (`generated_at`
excluded) — this is asserted by an automated test on the JSON artifact, not
inferred from the engine's design. Two audits of the same log will diff
clean. <!-- src: MP-7 resolved: T-REP-03/08 deterministic JSON tests -->

## Detector efficacy (measured today)

Golden-fixture precision: each detector reproduces its hand-derived dollar
figure exactly, and the clean-traffic fixture produces zero findings
(false-positive guard). All six rows below are pinned by the test suite at
the current milestone: <!-- src: MP-8 resolved at D5; pricing_golden_NOTES.md -->

| Detector | Golden monthly impact | Pinned by |
|---|---|---|
| D1 oversized model | $1.35 | exact-value test vs independent derivation |
| D2 missing cache | $0.246784 | same |
| D3 prompt bloat | $0.50 | same |
| D4 retry storm | $0.0510 | same |
| D5 unbounded max_tokens | $0.00 (informational, by design) | same |
| D6 chatty loop | $0.096 | same |

## Honest limitations

- Golden precision proves arithmetic correctness on engineered traffic; recall
  on messy real-world logs is being calibrated in founder-run dogfood audits
  before public claims are made about it.
- The measured run above used a development workstation; the 10-minute/1M-row
  requirement is bound to a 4-vCPU VPS and will be re-verified on production
  hardware at deploy.
- The F7 fixture is synthetic. Synthetic traffic proves throughput and
  arithmetic at scale, not real-world detector recall — that calibration
  happens in founder-run dogfood audits.
