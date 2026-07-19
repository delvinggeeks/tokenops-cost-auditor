# Performance

## The target

The specified requirement: a 1-million-row JSONL export processes in at most
11 minutes on a single 4-vCPU VPS — the machine class the product actually
runs on, not a benchmark rig. The bound was originally 10 minutes; the
production box measured 4% over it, so we published the honest number and
amended the spec upward — never the reverse.
<!-- src: NFR-04 as amended by founder 2026-07-20 (D13 deploy measurement) -->

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
The pipeline is effectively single-core (pandas), so the workstation headroom
is large; the production-hardware runs below are the numbers that bind.

## Measured on production hardware (D13 deploy, 2026-07-19)

Same fixture class, measured end-to-end through the live HTTPS path (upload
→ processing → done), on the production box: Contabo Cloud VPS 4 — x86,
4 vCPU, 7.8 GiB RAM, Ubuntu 24.04, full Docker stack (Caddy, Postgres and
the cron sidecar co-resident on the same machine).
<!-- src: NFR-04 amended bound; D13 VPS re-validation, CHANGELOG 2026-07-19 -->

| Run | Wall-clock | Peak memory |
|---|---|---|
| 1M rows, single audit | **624 s** (bound: 660 s, amended) | 2.25 GiB (app container) |
| 2 × 1.3M rows (195 MB each), concurrent | 34 m 20 s (both complete) | 5.14 GiB app + 150 MiB Postgres, of 7.8 GiB |

The 4-vCPU box is roughly 7× slower than the workstation — stated because
both numbers are real; the VPS row is the one that reflects what production
does. Audits run asynchronously (upload, then a signed report link by
email), so wall-clock here is turnaround time, not a request timeout.

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
- The stage-by-stage table used a development workstation; the binding
  measurement is the production-hardware section above, re-verified at the
  D13 deploy (and 4% over the original bound — which is why the bound moved,
  not the number).
- The F7 fixture is synthetic. Synthetic traffic proves throughput and
  arithmetic at scale, not real-world detector recall — that calibration
  happens in founder-run dogfood audits.
