# v4 wiring conditions (from the mockup ux gate, PASS-WITH-NOTES)

Fixed in the mockups already:
1. Brand mark now matches across both shells. The rule is duplicated in each
   mockup's <style>; WIRING must promote it into wa-design.css next to
   `.sidebar .brand` so the two shells read one definition, not two copies.
3. `aspect-ratio: 16/10` + `object-fit` pinned on `.hero-shot img`, not only on
   the placeholder, so a real capture cannot shift the hero fold.
4. Legal clause 2 now quotes FR-23 verbatim.

Carried to wiring as acceptance criteria — NOT yet satisfied:

- **f.2 — the hero must contain the one number.** The three-second rule fails
  in the first fold while the hero image is a placeholder. The real capture of
  /dashboard MUST show the verified-savings hero figure. A screenshot of an
  empty or zeroed dashboard satisfies the file but fails the rule.
- **FR-23 in the shipped Terms.** `templates/legal/terms.html` currently
  paraphrases the canonical string ("nothing IS retained... YOUR DATA IS never
  used"). Canonical, as pinned by tests, is:
  `analyzed then deleted; nothing retained beyond 7 days; never used for training`
  Bring terms.html onto it and extend the FR-23 test to cover terms, not just
  privacy/landing/docs-home. This is the same failure mode as the ₹20,000
  price: the binding document restating a published promise in its own words.
- **Screenshot capture step.** Firefox headless is available on this machine:
  run the preview, sign in, capture /dashboard at 1440px wide.
- **Test impact to expect when wiring.** `test_polish.py` / `test_auth.py` pin
  `class="cta"` count == 1 on the landing and the presence of 79%/98% with the
  40-60%/73% ban. The v4 landing keeps exactly one `.cta` and both attributed
  stats. Adding our own 32.5%/$8,757.75 figures requires the mandatory rails,
  which the mockup carries verbatim — keep them adjacent when wiring.
