# Stack

Every dependency was chosen deliberately, and additions require explicit
approval — the dependency list is a decision record, not an accretion.
<!-- src: PLAN.md §0.2; R-DEPS ruling -->

## Runtime

| Choice | Why |
|---|---|
| Python 3.14 | Pinned everywhere (pyproject, Dockerfile, CI); wheel availability for the full dependency set was verified before adoption, not assumed. |
| FastAPI + uvicorn | Typed request handling, OpenAPI for free (our API reference is generated from it), BackgroundTasks covers v1 processing without a queue. |
| pandas + pyarrow | The engine is columnar arithmetic over call frames; vectorized token math is both faster and easier to verify than row loops. |
| Postgres 17 | Boring, durable, additive-migration friendly. Compose-internal only — never exposed on a public port. |
| WeasyPrint | Server-side PDF from the same HTML the web report renders — one template, two artifacts. |
| uv | Locked, reproducible installs; `uv run` is the only sanctioned way to execute project tooling (a gate rule — findings from any other interpreter are invalid by definition). |

<!-- src: PLAN.md §0.2 verification evidence; TE-11 R-TOOLCHAIN -->

## What is deliberately absent

**No LLM SDK anywhere in the product path.** The engine cannot call a model,
so it cannot hallucinate a finding, leak a log, or bill you twice for your own
tokens. "Deterministic by construction" is our core reliability feature, and
it is enforced by a test, not a slogan. <!-- src: NFR-01; T-NFR-01 -->

**No payment SDKs.** Webhook verification is ~30 lines of stdlib HMAC per
provider; two full SDKs would be a larger attack surface than the feature.
<!-- src: PLAN §0.2 PAYMENT-SDKS -->

**No frontend framework.** Server-rendered Jinja templates and one stylesheet.
The report is the product; the pages around it are deliberately plain
(X-05 forbids an SPA). <!-- src: X-05 -->

**No analytics or trackers** — on the product or on this docs site.
