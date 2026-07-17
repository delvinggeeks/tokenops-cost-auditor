# Performance

## The target

The specified requirement: a 1-million-row JSONL export processes in under 10
minutes on a single 4-vCPU VPS. That is the machine class the product actually
runs on — not a benchmark rig. <!-- src: NFR-04, target as specified -->

!!! warning "MEASUREMENT-PENDING (MP-6)"
    Measured results — 1M-row wall-clock with machine spec, per-stage timings,
    memory peak — will be published here from the nightly performance run.
    FOUNDER PRECONDITION: at least one successful scheduled nightly perf run
    must exist before this section carries numbers; none has run yet at the
    D10 milestone. No performance number on this page will ever come from an
    untracked local run.

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
- Throughput numbers await the nightly run (above). The 10-minute/1M-row
  target is stated as the requirement it is, not as a result.
