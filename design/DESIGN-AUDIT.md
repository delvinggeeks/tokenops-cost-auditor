# Design deep-audit (founder order 2026-07-26) — REMEDIATED

Phase 3 complete: every P1 and P2 below is FIXED; its after-screenshot lives
at the same name under design/evidence/after/. P3s are recorded in BACKLOG.md
under "Design-audit P3s". Fix locations were kit/token-first as ordered:
F3/F6/F9/F10 landed in wa-design.css; F1 in the savings composition + one kit
grid; F2 in the two trend widgets (shared sparkline grammar); F4 in the KIT
ribbon macro (the hand-rolled dashboard copy is deleted); F5/F7 are one-line
screen edits; F8 in tour.js. Guard added: `var(--serif)` may never again have
consumers in wa-design.css (tests/test_design_tokens.py).

STATUS PER FINDING: F1 FIXED · F2 FIXED · F3 FIXED (+test) · F4 FIXED ·
F5 FIXED · F6 FIXED · F7 FIXED · F8 FIXED (popover anchors to its spotlight,
never clipped at the fold — asserted in the capture) · F9 FIXED · F10 FIXED ·
F11–F15 → BACKLOG.

Original audit text follows unchanged, for the before/after read.

Scope per the order: composition, density, hierarchy, craft. The mood/token/
kit architecture and R-LOOK-FINAL's hybrid are settled and not re-litigated.
Evidence: design/evidence/before/ (22 screenshots, captured 2026-07-21 UTC
from the seeded preview at commit c20d252). Each finding cites its screenshot.
Severity: P1 = undermines trust or hierarchy on a money surface; P2 = visibly
unfinished craft or density failure; P3 = polish, recorded to BACKLOG.

The sample report (/sample) inherits the WP-REPORT-VISUAL deferral (V-D9
founder ruling) — audited only for breakage (none found); its polish belongs
to that milestone. [sample-desktop-sanchaya.png]

## P1 — fix in this round, kit-first

**F1 · HIERARCHY/DENSITY · SavingsHero floats in dead space.**
[dashboard-desktop-sanchaya.png] The verified figure — the single element the
whole product exists to earn — sits left-aligned in a full-width surface whose
right ~60% is empty air. At 1440px the eye lands on a void, not on supporting
proof. Grammar: Stripe's balance overview pairs the headline balance with its
supporting figures in one dense band. FIX (kit + screen): savings surface
becomes a two-zone grid — hero (figure + double rule + badges + CTA) left,
three flat stat cards right (identified estimate, applied awaiting proof,
customer-reported), all from data the widget already receives.

**F2 · CHART CRAFT · trend charts read as unfinished sketches.**
[dashboard-desktop-sanchaya.png] Each chart shows one orphan axis label
($303 / 40%), no first/last values, no endpoint marker, and a line floating
in ~70% empty plot height. An enterprise buyer reads charts as competence
signals (Datadog sparkline grammar: endpoint dot + value, bounded axis labels,
tight plot). FIX (kit CSS + widget markup): endpoint dot + end-value label,
min/max axis labels, reduced plot height, subtle area fill under the line —
tokens only, flat per the hybrid law.

**F3 · TYPE/CONSISTENCY · the superseded serif is alive inside a signature.**
[dashboard-desktop-sanchaya.png — ribbon values "1 source(s)", "30 days",
"4 findings"] `.ribbon .seg .stage-state` and `.chip .v` still set
`font-family: var(--serif)` (wa-design.css:294, 340) — the face R-LOOK-FINAL
retired, rendering inside the pipeline ribbon, a §4 SIGNATURE. Same disease
class as the `.money` duplicate that survived the look swap. FIX: both rules
move to `--sans`; a test forbids `var(--serif)` consumers in wa-design.css
outside the token block (the report's own stylesheet is exempt per its
deferral).

## P2 — fix in this round

**F4 · COMPOSITION · the signature ribbon has TWO implementations.**
[dashboard-desktop-sanchaya.png] The dashboard hand-rolls `.ribbon .seg
.stage-state`; the kit ships `pipeline_ribbon()` with different markup. One
signature must have one implementation or the next re-skin forks it. FIX:
extend the kit macro to carry per-stage value/sub lines; dashboard composes
it; the orphaned `.seg` CSS is deleted.

**F5 · HIERARCHY · four primary Applied buttons in one table.**
[dashboard-desktop-sanchaya.png] Repeating the loudest weight four times in
adjacent rows makes nothing primary (Linear row-action grammar: row actions
are quiet; the drawer's single confirmed action carries the weight). FIX:
row-level Applied becomes quiet; primary stays on the drawer's Applied.

**F6 · DENSITY/SCALE · small widgets are half air with body-size values.**
[dashboard-desktop-sanchaya.png] "4 days" (next audit) renders at body size;
the sources widget holds one row and a void. Stat values must sit on the stat
scale (money-lg) consistently; sources gains its next-pull line from data the
metric already returns. FIX in widget templates + one kit class.

**F7 · DENSITY · wizard at-limit state is a message in a void.**
[wizard-step2-desktop-sanchaya.png] The at-limit branch centers two lines in a
panel sized for the absent form (~70% dead). FIX: compose kit.empty_state,
compact panel, keep the encryption note adjacent.

**F8 · CRAFT · tour popover is disconnected from its spotlight.**
[tour-midstep-desktop.png] Step 2 spotlights the hero mid-page while the
popover sits fixed bottom-left over the sidebar — the reader must find the
target themselves (defeats recognition-over-recall). FIX (tour.js): position
the popover adjacent to the spotlighted element, clamped to viewport; corner
fallback under 720px.

**F9 · CRAFT · the drawer's money input is a bare browser control.**
[findings-drawer-desktop-sanchaya.png] The optional "saw a figure" input is an
unstyled ~90px box inline in a sentence — the one form control on the money
surface reads default-browser (checklist c/e). FIX: field styling (right-
aligned tabular, framed, focus ring) via the kit field classes.

**F10 · A11Y · mobile tap targets under 44px.**
[dashboard-mobile-sanchaya.png] Sidebar/nav links compute to ~28px height;
buttons ~36px. FIX: ≥44px min target height under 720px via one media block
in wa-design.css. Focus-visible ring verified present globally (218) — pass.

## P3 — recorded to BACKLOG, not fixed now

**F11** Severity chips read as debug badges (mono caps in boxes); consider
dot+word per Linear label grammar. [findings-desktop-sanchaya.png]
**F12** Sort glyphs in findings headers are cropped/small. [same]
**F13** Sample-report stat-card label wrapping → WP-REPORT-VISUAL (already
its own milestone). [sample-desktop-sanchaya.png]
**F14** `.nav-group a` declared twice (236 + density pass) — consistent
values today; consolidate when touched next.
**F15** Landing mobile: hero screenshot sits below the fold; acceptable
(copy + CTA are above), revisit with post-launch funnel data.
[landing-mobile.png]

## Checklist verdicts per screen (h — Nielsen one-liners)

- dashboard: status visibility STRONG (freshness stamp, provenance lines);
  hierarchy WEAK pre-F1/F2; consistency WEAK pre-F3/F4. [dashboard-*]
- findings + drawer: match-to-world STRONG (plain headlines, jargon at depth
  c); recognition STRONG (row→drawer grammar); craft gap F9. [findings-*]
- wizard: guidance copy STRONG; density gap F7. [wizard-step2-*]
- billing/settings: consistent kit tables, honest states — PASS (badge fixed
  in wiring round). [billing-*, settings-*]
- statements: artifact-verbatim <pre> is deliberate honesty (never rewritten)
  — PASS. [statement-detail-*]
- landing: above-the-fold carries what-it-is + real labeled screenshot +
  single primary CTA within one 1440 viewport — PASS per R-LANDING-2 anatomy;
  aesthetic-minimalist PASS (one delight per section). [landing-desktop.png]
- aura mood: legibility holds on all captured aura screens; AA remains
  computed-enforced per mood. [dashboard/findings/billing-desktop-aura.png]

## Evidence limitations

The wizard's step-2 key-paste form could not render (seeded account is at its
1-source limit; the at-limit state IS finding F7). The statement email body is
the archived artifact and is exempt from restyling by design.
