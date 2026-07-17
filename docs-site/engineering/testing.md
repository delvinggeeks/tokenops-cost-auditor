# Testing

The suite's job is to make wrong money math impossible to ship. Everything
else is secondary. <!-- src: docs/05-TEST-PLAN.md -->

## Golden fixtures: known waste in, exact findings out

The core strategy is black-box: engineered fixtures plant exactly one specimen
of each waste class, and tests assert the engine reports each finding at an
exact, hand-derived dollar figure — down to the sixth decimal
($0.246784/month for the cache golden). The derivations were computed
independently of the engine (spreadsheet arithmetic first, engine second) and
human-verified against provider rate pages; they live in the repository next
to the fixtures. <!-- src: pricing_golden_NOTES.md; tests/test_rules.py -->

This independence matters: during development, the independent derivation
caught a real engine bug (a timestamp-resolution change collapsing 13 cache
windows into 1) that same-source testing would have baked in as "expected."

## The false-positive guard

A `clean_optimal` fixture — traffic engineered to be efficient — must produce
**zero findings**. Detector precision is a test, not a claim.

## Money-math discipline

Any change to pricing or estimator code requires updating the golden files in
the same commit, with a spreadsheet diff referenced in the commit message.
The cost-assembly modules are held at 100% line coverage; reconciliation
property tests assert priced totals match the assembled report within ±0.5%.
<!-- src: CLAUDE.md rule 4; NFR-07 -->

## The import guard

A static AST test walks `services/rules` and `services/pricing` and fails on
any network or LLM import. The privacy and determinism claims on this site are
backed by this test. <!-- src: T-NFR-01 -->

## Layers

L1 unit tests run on SQLite for speed; L2 integration runs against real
Postgres in CI; L3 exercises the API surface through the ASGI test client
(auth, payment gates, idempotency, rate limits, error envelopes); L4 is the
CLI end-to-end (fixture in, PDF out); L5 is nightly performance
(see [Performance](performance.md)). Suite size at the D10 milestone:
171 tests + 1 CI-only Postgres case. <!-- src: docs/05 §1; STATUS.md D10 -->

## Definition of done

Verbatim from the build plan — the exit criteria every milestone meets before
the next begins:

> Universal exit criteria for every Dn: suite green locally + CI,
> docs/04-TRACEABILITY.md updated in the same commit as each implemented
> requirement, STATUS.md paragraph written, context cleared per TE-9 before
> Dn+1; the group's gate sweep must PASS before the group branch merges to
> main. <!-- src: PLAN.md §1 intro, verbatim -->
