# Standards

We build against open telemetry and billing-data standards rather than
inventing private formats, so your data meets us where it already lives.

## OpenTelemetry GenAI semantic conventions

Our ingestion contract maps token-usage telemetry — the `gen_ai.*`
attribute family from the OpenTelemetry GenAI semantic conventions — onto
the same internal record format our upload path uses. The conventions are
still marked experimental upstream, so the mapping handles attribute
renames across versions rather than pinning one snapshot.

One rule carries over from everything else we do: **prompt and completion
content attributes are dropped at ingest**. The counts-only law that
governs uploads (nothing but token counts, metadata, and hashes is ever
stored) applies at the door for telemetry too — it is not a
post-processing step.

## FOCUS

Report JSON and aggregate exports are designed to align with FOCUS (the
FinOps Open Cost and Usage Specification) so audit output can sit next to
your existing cost data instead of beside it in a proprietary shape.

## Status, stated plainly

Today the product ingests files (upload and CLI). The standards
commitments above are recorded design constraints for the connector tiers
on our roadmap — written down now so the contracts are stable before the
code exists, the same way our pricing table and detector formulas were
specified before implementation.
