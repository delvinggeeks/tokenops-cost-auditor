# Motion specs — the gate artifact (R-MOTION-SPEC, founder 2026-07-24)

Every animated effect is specified HERE before it is implemented. ux-reviewer
checks the implementation against this sheet; an effect in the code that is not
on this sheet is a gate finding, and so is an effect on this sheet that does not
serve comprehension or a money-moment.

Each row names its implementation identifier where one exists, so a reviewer
can get from this sheet to the code without guessing.

Format per effect: **trigger · behavior · duration+easing · reduced-motion
fallback · tokens used**.

## Standing rules

- Budget: UI motion 150–250ms; the hero count-up alone may take 600ms.
- Tokens only. Motion introduces no colour, shadow or radius that is not
  already a `wa-design.css` variable. If an effect seems to need a new token,
  that is a design decision and goes through the design gate, not the motion one.
- **One designed delight per section.** Motion that does not serve
  comprehension or the money-moment is cut at the gate (R-DESIGN-ADDENDUM 3,
  restated by R-MOTION-SPEC 3).
- Reduced motion is not a downgrade path bolted on afterwards: each effect
  states what renders *instead*, and that state must be complete on its own.

### How reduced-motion is enforced

`wa-design.css` carries a single global block:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
  .countup { --n: var(--target); }
}
```

Because it is `*` + `!important`, it also disarms effects declared in
`wa-public.css` and in any future stylesheet, regardless of load order —
`!important` beats a normal declaration whatever the cascade. New stylesheets
therefore inherit the protection and must NOT ship their own copy; one
definition, one place. JS-driven effects do not get this for free and must
check `matchMedia("(prefers-reduced-motion: reduce)")` themselves — noted per
effect below.

---

## A. Shipped — in-app (audited against the running code)

| # | Effect | Trigger | Behavior | Duration + easing | Reduced-motion | Tokens |
|---|--------|---------|----------|-------------------|----------------|--------|
| A1 | Card lift | pointer hover | `box-shadow` `--lift-1`→`--lift-2`, `translateY(0→-1px)` | `--t-fast` (150ms) `--ease` | transition removed; hover shadow applies instantly | `--lift-1/2`, `--inner-edge`, `--ease`, `--t-fast` |
| A2 | Button press | pointer/keyboard activate | `scale(1→0.98)` | `--t-fast` `--ease` | instant | `--t-fast`, `--ease` |
| A3 | Evidence expander (`@keyframes spring-open`) | click on `summary` | opacity 0→1, `translateY(-4px)→0`, `scaleY(.98→1)` | `--t-med` (250ms) `--ease` | content appears open, no spring | `--t-med`, `--ease` |
| A4 | htmx swap-in (`@keyframes swap-in`) | partial swap | opacity 0→1, `translateY(4px→0)` | `--t-fast` `--ease` | swapped content appears | `--t-fast`, `--ease` |
| A5 | Hero count-up (`@keyframes countup`) | page load, once | counter 0→target | 600ms `--ease` | **final number rendered immediately** via `.countup { --n: var(--target) }` | `--ease` |
| A6 | Pipeline stage pulse (`@keyframes stage-pulse`) | audit in progress | ring `box-shadow` pulse on the active stage | 1.6s loop `--ease` | static ring on the active stage | `--accent` at 25% alpha |
| A7 | Ledger row tint | pointer hover | `background`→`--surface-tint` | `--t-fast` `--ease` | instant tint | `--surface-tint` |

**A6 note.** Reused by the pipeline theater's `.seg.live .stage-name`
(R-PIPELINE-UI-SEQ): the same keyframe animates box-shadow there too — the
ring wraps the stage NAME rather than the stage card. A 1.6s infinite loop sits outside the 150–250ms budget by design:
it is a *status* indicator, not a transition, and it stops when the audit
finishes. Called out here rather than left as an unexplained exception.

## B. Shipped — v4 unified surfaces

| # | Effect | Trigger | Behavior | Duration + easing | Reduced-motion | Tokens |
|---|--------|---------|----------|-------------------|----------------|--------|
| B1 | Upload dropzone focus | hover / `focus-within` | `border-color` `--rule`→`--accent`, `background` `--surface`→`--surface-tint` | `--t-fast` `--ease` | colours change instantly — the affordance still reads | `--rule`, `--accent`, `--surface`, `--surface-tint` |
| B2 | Sources drawer | click "Details" | row `hidden` toggles | none (instant) | identical — there is no motion to remove | — |

**B2 is deliberately unanimated.** The drawer carries the engineer's evidence;
animating a disclosure that a user opens repeatedly adds latency to a
comprehension task. The delight budget for `/sources` is spent on the status
dot and badge, not on movement.

---

## C. Landing (R-LANDING-2) — SHIPPED 2026-07-25 in `static/land/landing.js`.

Implemented exactly as specified below; the ux gate checks the code against
this table. All five gate on `prefers-reduced-motion` in JS (the global CSS
block cannot stop a script), default to final-state-visible, and C1 is the
only pointer listener (hero-scoped, rAF-throttled).

| # | Effect | Trigger | Behavior | Duration + easing | Reduced-motion | Tokens |
|---|--------|---------|----------|-------------------|----------------|--------|
| C1 | **Hero tilt** (the one 3D moment) | pointer move over hero; falls back to a static tilt with no pointer | screenshot rotates within ±6° Y / ±3° X about `left center`, following pointer at reduced amplitude | continuous follow, 120ms `--ease` catch-up | **static, untilted, flat screenshot** — no perspective, full `--lift-3` | `--lift-3`, `--inner-edge`, `--rule`, `--ease` |
| C2 | Section reveal | IntersectionObserver, element 15% in view, fires once | opacity 0→1, `translateY(12px→0)` | 200ms `--ease` | elements render final-state visible; observer never attaches | `--ease` |
| C3 | Pipeline stage light-up | scroll position within the pipeline section | each stage's rule goes `--rule`→`--accent`, label `--ink-soft`→`--ink`, in sequence | 200ms `--ease` per stage | **all five stages render lit** — the sequence is decorative, the content is not | `--rule`, `--accent`, `--ink`, `--ink-soft` |
| C4 | Product-tour count-ups | tab panel becomes visible | figures count 0→target | 600ms cubic ease-out in JS (a computed curve cannot read `--ease`; it approximates it — same exception class as A6's loop) , once per panel | final figures rendered immediately; JS resolves to the exact markup value | none (JS-computed curve) |
| C5 | Tab switch | click/keyboard on tab | panel cross-fades opacity 0→1 | 150ms `--ease` | instant swap | `--ease` |

**Implementation constraints for C1–C5**

- All JS effects must gate on
  `window.matchMedia("(prefers-reduced-motion: reduce)").matches` and return
  early — the CSS block above does not stop a script from mutating styles.
- IntersectionObserver reveals must set the final state when the observer is
  unsupported or disabled. A visitor must never be left with `opacity: 0`
  content because a script failed; default to visible, animate down from there.
- C1 attaches a pointer listener to the hero only, throttled to
  `requestAnimationFrame`. No scroll listener on `document`.
- Total landing JS budget < 15KB, per R-LANDING-2.
- C2 carries a TOP-TO-BOTTOM INVARIANT (ux gate note, 2026-07-25): revealing
  any section force-reveals every section above it. Jump scrolls (End key,
  anchor links, fast flings) can skip an element's intersecting frame
  entirely, and a reader must never find a void where a section belongs. The
  reveal order is the document order, so nothing above a revealed section may
  stay hidden.

**C6–C8 — the enterprise elevation round (founder walkthrough, 2026-07-27).**

| # | Effect | Trigger | Behavior | Duration + easing | Reduced-motion | Tokens |
|---|--------|---------|----------|-------------------|----------------|--------|
| C6 | The dollar's journey (workflow flow-line) | IntersectionObserver, pipeline section 30% in view, once | an SVG ledger line draws left→right through the five stages (stroke-dashoffset), carrying the money story raw spend → verified | 900ms `--ease` | line renders fully drawn | `--accent`, `--rule` |
| C7 | Double rule draw (self-audit figure) | section 40% in view, once | the accountant's double rule draws under 32.5% (two strokes, dashoffset) | 400ms `--ease` | rule renders complete | `--rule-strong` |
| C8 | Hero entrance | page load, once | eyebrow → h1 → subhead → CTAs → proof chips rise 8px + fade, 60ms stagger | 200ms each `--ease` | all render in final position | `--ease` |

C6/C7 are comprehension motion (the money's path; the verified total's rule —
the §4 signature earning its place on the landing). C8 is the one orchestrated
page-load moment. All three gate on prefers-reduced-motion in JS and default
to the finished state.

**C9 — hero depth scene (founder walkthrough round 3, 2026-07-27).**

| # | Effect | Trigger | Behavior | Duration + easing | Reduced-motion | Tokens |
|---|--------|---------|----------|-------------------|----------------|--------|
| C9 | Hero depth float (`@keyframes hero-float`) | ambient, on load; suspended while the pointer drives C1 | the layered scene (dashboard exhibit + two floating stat cards at translateZ depths) drifts ±4px / ±0.4° in slow alternation — the 3D moment breathing | 6s ease-in-out infinite alternate | static, layered, full lift — depth reads from shadows alone | `--lift-2/3`, `--ease` |

C9 extends the ruled 3D moment (R-LANDING-2 §1), not the cut-listed parallax:
one scene, one ambient motion, and C1's pointer tilt takes over on hover.
The float cards carry the fold's live figures (labeled sample data) as TYPE,
not pixels — closing the elevation gate's hero note.

**Cut list — considered and rejected.** Parallax on the hero (fights the tilt,
two competing depth cues), number odometer roll on scroll-back (re-animating a
figure the reader already read implies it changed), and card entrance stagger
on the plans grid (three cards is not a sequence; staggering implies order that
does not exist).
