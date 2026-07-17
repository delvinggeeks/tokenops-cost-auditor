# Traceability

Every requirement maps to the design element that satisfies it, the module
that implements it, and the test IDs that prove it — and the matrix is updated
in the same commit as the implementation, by rule. This page includes the live
matrix from the repository, so it cannot drift from what ships.
<!-- src: CLAUDE.md rule 5; docs/04 transcluded below via snippets -->

## Why this discipline

An audit product's credibility is its chain of evidence. When the report says
"savings estimates are conservative by construction," you should be able to
walk from that sentence to the requirement (FR-08), to the estimator code, to
the golden test pinning the exact dollar output for a known input. The matrix
below is that walk, for every requirement.

## The live matrix

--8<-- "docs/04-TRACEABILITY.md"
