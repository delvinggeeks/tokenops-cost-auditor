"""Compose the v3 mockups from shared shell pieces (mirrors how the SSR
partials will be assembled at V-D4). Emits design/mockups/v3/*.html."""

from pathlib import Path

ROOT = Path("/home/lokesh/Desktop/tokenops-cost-auditor")
OUT = ROOT / "design/mockups/v3"
OUT.mkdir(parents=True, exist_ok=True)
SPRITE = (ROOT / "design/icons.svg").read_text(encoding="utf-8").split("\n", 3)[3]

NAV = [
    ("Monitor", [("i-overview", "Overview"), ("i-findings", "Findings"),
                 ("i-reports", "Reports &amp; audits")]),
    ("Connect", [("i-source", "Sources"), ("i-upload", "Get your logs")]),
    ("Act", [("i-alert", "Alerts"), ("i-statement", "Savings statements")]),
    ("Help", [("i-guide", "Guide"), ("i-replay", "Replay tour"),
              ("i-method", "Documentation")]),
    ("Account", [("i-settings", "Settings"), ("i-billing", "Billing")]),
    ("Engineering", [("i-detector", "Detector detail"), ("i-method", "Methodology")]),
]


def icon(name, cls="i"):
    return f'<svg class="{cls}" aria-hidden="true"><use href="#{name}"/></svg>'


def sidebar(active):
    out = ['<aside class="sidebar" aria-label="Sections">',
           '    <div class="brand">TokenOps Cost Auditor</div>']
    for group, items in NAV:
        out.append('    <nav class="nav-group">')
        out.append(f'      <div class="label">{group}</div>')
        for ic, label in items:
            cur = ' aria-current="page"' if label == active else ""
            out.append(f'      <a href="#"{cur}>{icon(ic)}{label}</a>')
        out.append("    </nav>")
    out.append("  </aside>")
    return "\n  ".join(out)


def topbar(page, plan, fresh):
    return f"""<header class="topbar">
      <button class="btn btn-quiet sidebar-toggle" aria-expanded="true" aria-label="Menu">{icon('i-menu')}</button>
      <strong>TokenOps Cost Auditor</strong>
      <span class="muted">{page}</span>
      <span class="plan-badge">{plan}</span>
      <span class="spacer"></span>
      <span class="freshness">{fresh}</span>
      <button class="btn btn-quiet">lokesh@…</button>
    </header>"""


def help_pop(what, where, dowhat, link="Learn more"):
    return f"""<details class="help">
          <summary aria-label="What is this?">?</summary>
          <div class="help-body">
            <dl>
              <dt>What this shows</dt><dd>{what}</dd>
              <dt>Where the number comes from</dt><dd>{where}</dd>
              <dt>What to do with it</dt><dd>{dowhat}</dd>
            </dl>
            <a href="#">{link} →</a>
          </div>
        </details>"""


def head(title):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="../../wa-design.css">
</head>
<body>
{SPRITE}"""


# ---------- charts (real SVG, gridlines + axis labels; §1b) ----------
SPEND_PTS = [(0, 88), (28, 84), (56, 92), (84, 74), (112, 70), (140, 78),
             (168, 62), (196, 66), (224, 55), (252, 50), (280, 46), (308, 40)]
WASTE_PTS = [(0, 24), (28, 27), (56, 22), (84, 30), (112, 28), (140, 36),
             (168, 44), (196, 52), (224, 62), (252, 68), (280, 74), (308, 78)]


def area_chart():
    pts = " ".join(f"{x},{y}" for x, y in SPEND_PTS)
    poly = f"0,120 {pts} 308,120"
    grid = "".join(
        f'<line class="grid-line" x1="34" y1="{y}" x2="342" y2="{y}"/>'
        f'<text class="axis-label" x="0" y="{y + 3}">${lab}</text>'
        for y, lab in ((20, "12k"), (50, "9k"), (80, "6k"), (110, "3k"))
    )
    xlab = "".join(f'<text class="axis-label" x="{34 + x}" y="134" text-anchor="middle">{d}</text>'
                   for x, d in ((0, "Jun 21"), (112, "Jul 1"), (224, "Jul 11"), (308, "Jul 21")))
    return f"""<svg class="chart" viewBox="0 0 342 140" role="img"
            aria-label="Spend per day over 30 days, rising from about $6,100 to $8,900">
            {grid}
            <g transform="translate(34,0)">
              <polygon class="area" fill="var(--accent)" points="{poly}"/>
              <polyline class="plot draw" stroke="var(--accent)" points="{pts}"/>
            </g>
            {xlab}
          </svg>"""


def line_chart():
    pts = " ".join(f"{x},{y}" for x, y in WASTE_PTS)
    grid = "".join(
        f'<line class="grid-line" x1="34" y1="{y}" x2="342" y2="{y}"/>'
        f'<text class="axis-label" x="0" y="{y + 3}">{lab}%</text>'
        for y, lab in ((20, "40"), (50, "30"), (80, "20"), (110, "10"))
    )
    xlab = "".join(f'<text class="axis-label" x="{34 + x}" y="134" text-anchor="middle">{d}</text>'
                   for x, d in ((0, "Jun 21"), (112, "Jul 1"), (224, "Jul 11"), (308, "Jul 21")))
    return f"""<svg class="chart" viewBox="0 0 342 140" role="img"
            aria-label="Waste share falling from 38 percent to 24.1 percent, now inside the 25 percent target band">
            {grid}
            <g transform="translate(34,0)">
              <rect class="target-band" x="0" y="80" width="308" height="40"/>
              <line class="target-line" x1="0" y1="80" x2="308" y2="80"/>
              <text class="axis-label" x="4" y="94" fill="var(--verified)">your target: 25%</text>
              <polyline class="plot draw" stroke="var(--waste)" points="{pts}"/>
            </g>
            {xlab}
          </svg>"""


def spark(points, stroke):
    pts = " ".join(f"{x},{y}" for x, y in points)
    return (f'<svg class="spark" width="100%" height="20" viewBox="0 0 100 20" '
            f'preserveAspectRatio="none" aria-hidden="true">'
            f'<polyline fill="none" stroke="{stroke}" stroke-width="1.5" points="{pts}"/></svg>')


CANON_D2 = "Your agent re-sends a 28,000-token prefix uncached, 1,900 times a day"

CHIPS = f"""<div class="chips w-12">
          <div class="chip"><div class="k">{icon('i-calls')} Calls audited</div>
            <div class="v">1.24M</div>
            {spark([(0,14),(20,12),(40,13),(60,9),(80,8),(100,6)], "var(--accent)")}</div>
          <div class="chip"><div class="k">{icon('i-source')} Sources</div>
            <div class="v">1<span class="muted" style="font-size:13px;font-family:var(--sans)"> of 1</span></div></div>
          <div class="chip"><div class="k">{icon('i-findings')} Findings open</div>
            <div class="v">8</div>
            {spark([(0,4),(20,6),(40,7),(60,9),(80,11),(100,12)], "var(--waste)")}</div>
          <div class="chip"><div class="k">{icon('i-check')} Fixes applied</div>
            <div class="v">3</div>
            {spark([(0,16),(20,16),(40,12),(60,12),(80,8),(100,5)], "var(--verified)")}</div>
          <div class="chip"><div class="k">{icon('i-alert')} Alerts armed</div>
            <div class="v">2</div></div>
        </div>"""


def ribbon(segs):
    out = ['<div class="ribbon">']
    for cls, name, state, note in segs:
        out.append(f'            <div class="seg {cls}"><div class="stage-name">{name}</div>'
                   f'<div class="stage-state">{state}</div>'
                   f'<div class="stage-note">{note}</div></div>')
    out.append("          </div>")
    return "\n".join(out)


LIVE_RIBBON = ribbon([
    ("active", "Input", "1 source", "OpenAI org · pulled 06:15 UTC"),
    ("active", "Analyze", "1.24M calls", "Audited 06:30 UTC · 31 days"),
    ("active", "Report", "11 findings", "$2,931.20/mo identified"),
    ("active", "Act", "3 applied", "$1,284.40/mo verified"),
    ("waiting", "Prevent", "2 armed", "Spend spike · waste above 25%"),
])

EMPTY_RIBBON = ribbon([
    ("active", "Input", "Start here", "Connect a provider or upload a log export"),
    ("waiting", "Analyze", "Waiting", "Six detectors at a verified rate card"),
    ("waiting", "Report", "Waiting", "Findings ranked by dollars"),
    ("waiting", "Act", "Waiting", "Apply a fix, we verify the saving"),
    ("waiting", "Prevent", "Waiting", "Alerts watch between audits"),
])

FOOT = """      <p class="muted" style="margin-top: var(--s4); font-size: 13px;">%s</p>
    </main>
  </div>
</div>
</body>
</html>"""

# ============================== OVERVIEW ==============================
overview = f"""{head('Mockup v3 — Overview (R-DESIGN-V3) — SAMPLE DATA')}
<!-- MOCKUP v3, sample data. Icons from the self-hosted sprite; charts are
     real SVG with axes and gridlines; every widget carries a "?" help
     popover whose copy comes from the shared help registry at V-D4. -->
<div class="app">
  {sidebar('Overview')}
  <div>
    {topbar('Overview', 'Pro', 'Data as of <b>2026-07-21 06:30 UTC</b> · audit <code>a7f2…c91</code>')}
    <main class="main">
      <div class="grid">

        <!-- W0 is deliberately NOT a .widget: the ribbon is a full-bleed spine
             with its own 1px chrome; wrapping it would double the border
             (mockup-v3 ux gate f.4 — confirmed intentional). -->
        <section class="w-12">
          <div class="widget-head">
            {icon('i-detector', 'i i-lg')}<h2>Your pipeline, right now</h2>
            {help_pop("The five stages of the loop, with live state from your account.",
                      "Stage counts read from your sources, the latest audit, your applied findings and armed alert rules.",
                      "Look for the stage that is waiting — that is where your next minute is best spent.",
                      "How TokenOps works")}
          </div>
          <p class="tells">What this tells you: where your money is in the loop — from
            logs coming in to alerts watching for the next surprise.</p>
          {LIVE_RIBBON}
        </section>

        <section class="widget w-12" aria-labelledby="w1">
          <div class="widget-head">
            {icon('i-savings', 'i i-lg')}<h2 id="w1">Verified savings — July 2026</h2>
            {help_pop("Money you are no longer spending, proven by a later audit of your own logs.",
                      "Each applied finding is recomputed on the next audit covering at least 7 days; the difference, capped at the original estimate, is summed here.",
                      "Apply more findings — each one converts an estimate into a verified number here.",
                      "How we verify savings")}
          </div>
          <p class="tells">What this tells you: money you are no longer spending,
            recomputed from your own logs after you applied fixes. Not a projection.</p>
          <div class="money-hero total-rule">
            $<span class="countup" style="--target: 1284;" aria-label="1,284 dollars"></span><span class="money-sm">.40</span>
          </div>
          <div style="margin-top: var(--s2);">
            <span class="badge badge-verified">{icon('i-check')} VERIFIED — 3 fixes, confirmed over 14 days</span>
            <span class="badge badge-estimate" style="margin-left: 8px;">$2,931.20/mo more identified (estimate)</span>
          </div>
          <p class="muted" style="margin: var(--s2) 0 0; font-size: 13px;">
            Customer-reported savings ($400.00) are tracked separately and never enter
            this figure.</p>
          <div style="margin-top: var(--s2);">
            <a class="btn btn-primary" href="#">Apply the next fix ($1,120.10/mo)</a>
            <a class="btn btn-quiet" href="#">How we verify savings</a>
          </div>
          <div class="provenance">Audit <code>a7f2…c91</code> vs baseline
            <code>3b90…447</code> · rate card v2026-07-17</div>
        </section>

        {CHIPS}

        <section class="widget w-6" aria-labelledby="w2">
          <div class="widget-head">
            {icon('i-trend-up', 'i i-lg')}<h2 id="w2">Spend trend</h2>
            {help_pop("Daily API spend across every connected source, last 30 days.",
                      "Priced from your provider's reported token counts at our human-verified rate card, not from your invoice.",
                      "A step change usually means a deploy — compare it against the findings list for the same week.",
                      "Reading your spend chart")}
          </div>
          <p class="tells">What this tells you: what you are paying now versus the last
            30 days.</p>
          <div class="money money-lg">$8,912.55<span class="muted" style="font-size: 14px; font-family: var(--sans);"> /mo run-rate</span></div>
          {area_chart()}
          <div style="margin-top: var(--s2);"><a class="btn btn-quiet" href="#">Break down by model →</a></div>
          <div class="provenance">30-day window · audit <code>a7f2…c91</code></div>
        </section>

        <section class="widget w-6" aria-labelledby="w3">
          <div class="widget-head">
            {icon('i-trend-down', 'i i-lg')}<h2 id="w3">Waste share</h2>
            {help_pop("The share of spend our detectors can account for as avoidable.",
                      "Sum of every open finding's monthly impact, divided by monthly spend, capped at 100%.",
                      "Set your target in Alerts — we tell you when the line leaves the band.",
                      "How waste share is calculated")}
          </div>
          <p class="tells">What this tells you: how much of that spend our detectors can
            account for as avoidable.</p>
          <div class="money money-lg" style="color: var(--waste);">24.1%</div>
          {line_chart()}
          <div style="margin-top: var(--s2);"><a class="btn btn-quiet" href="#">Set your waste target →</a></div>
          <div class="provenance">Falling since the caching fix, Jul 8 · audit
            <code>a7f2…c91</code></div>
        </section>

        <section class="widget w-8" aria-labelledby="w4">
          <div class="widget-head">
            {icon('i-findings', 'i i-lg')}<h2 id="w4">Top findings by monthly impact</h2>
            {help_pop("The largest avoidable costs found in your latest audit.",
                      "Each row is one detector's estimate for one route, priced at the verified rate card and scaled to 30 days.",
                      "Apply the top one. Its saving is re-verified on your next audit and moves into the headline.",
                      "Applying findings")}
          </div>
          <p class="tells">What this tells you: the biggest single things worth fixing,
            ranked by dollars, not severity labels.</p>
          <table class="ledger">
            <thead><tr>
              <th class="sortable">Finding {icon('i-sort')}</th>
              <th class="sortable">Severity {icon('i-sort')}</th>
              <th class="sortable money" aria-sort="descending">Monthly {icon('i-sort')}</th>
              <th></th>
            </tr></thead>
            <tbody>
              <tr><td>{CANON_D2}</td>
                <td><span class="sev sev-high">high</span></td>
                <td class="money">$1,120.10</td>
                <td><button class="btn btn-primary">Applied</button>
                    <button class="btn btn-quiet">Dismiss</button></td></tr>
              <tr><td>Frontier model on short completions (avg 92 tokens)</td>
                <td><span class="sev sev-med">med</span></td>
                <td class="money">$688.75</td>
                <td><button class="btn btn-primary">Applied</button>
                    <button class="btn btn-quiet">Dismiss</button></td></tr>
              <tr><td>Retry storms — needs per-request logs</td>
                <td><span class="sev sev-low">n/a</span></td>
                <td class="money muted">—</td>
                <td><a class="btn" href="#">{icon('i-upload')} Upload logs</a></td></tr>
            </tbody>
          </table>
          <div class="provenance">11 findings in audit <code>a7f2…c91</code> ·
            <a href="#">open the full findings table →</a></div>
        </section>

        <section class="widget w-4" aria-labelledby="w6">
          <div class="widget-head">
            {icon('i-clock', 'i i-lg')}<h2 id="w6">Next scheduled audit</h2>
            {help_pop("When these numbers refresh next.",
                      "Your plan's cadence, counted from the last completed audit.",
                      "Nothing — it runs itself. Apply fixes before it runs and the next audit measures them.",
                      "Scheduled audits")}
          </div>
          <p class="tells">What this tells you: when these numbers refresh next.</p>
          <div class="stat-lg">2 days</div>
          <p class="muted" style="margin: 4px 0 0;">Monday 06:30 UTC, weekly</p>
          <div class="provenance">Pro plan · source pulls daily 06:15 UTC</div>
        </section>

        <section class="widget w-4" aria-labelledby="w5">
          <div class="widget-head">
            {icon('i-source', 'i i-lg')}<h2 id="w5">Sources</h2>
            {help_pop("Every provider connection and whether it is still delivering data.",
                      "The last successful pull timestamp per connection.",
                      "If a source goes stale, re-connect it — the key may have been rotated or revoked.",
                      "Managing sources")}
          </div>
          <p class="tells">What this tells you: whether we are still receiving your usage
            data.</p>
          <p><span class="badge badge-verified">{icon('i-check')} healthy</span>
            <strong>OpenAI — production org</strong><br>
            <small class="muted">31 days of usage · pulled today 06:15 UTC</small></p>
          <a class="btn" href="#">Connect another source</a>
          <div class="provenance">1 of 1 connections used on Pro</div>
        </section>

        <section class="widget w-4" aria-labelledby="w7">
          <div class="widget-head">
            {icon('i-alert', 'i i-lg')}<h2 id="w7">Recent alerts</h2>
            {help_pop("Anything that crossed a threshold you set, between audits.",
                      "Rules are evaluated hourly against your latest pulled usage.",
                      "No alerts is the good outcome. Tighten a threshold if you want earlier warning.",
                      "Setting up alerts")}
          </div>
          <p class="tells">What this tells you: surprises we caught between audits.</p>
          <div class="empty">
            <p>No alerts in the last 30 days — your spend stayed inside the thresholds
              you set.</p>
            <a class="btn" href="#">Review alert thresholds</a>
          </div>
          <div class="provenance">2 rules armed · checked hourly</div>
        </section>

        <section class="widget w-4" aria-labelledby="w8">
          <div class="widget-head">
            {icon('i-statement', 'i i-lg')}<h2 id="w8">Savings statement</h2>
            {help_pop("A one-page monthly summary written for whoever signs off on the bill.",
                      "Verified savings for the month, with estimates labelled as estimates and customer-reported figures kept separate.",
                      "Forward it. It is designed to be read by someone who never logs in here.",
                      "Reading your Savings Statement")}
          </div>
          <p class="tells">What this tells you: the one-page summary you can forward to
            whoever signs off on the bill.</p>
          <p class="money money-sm">June 2026 · $980.15 verified</p>
          <a class="btn" href="#">Open statement</a>
          <a class="btn btn-quiet" href="#">Email it again</a>
          <div class="provenance">Next statement: 1 Aug 2026 · sent to lokesh@…</div>
        </section>

      </div>
{FOOT % ('MOCKUP v3 — sample data. Delight on this surface: the verified-savings '
         'count-up, and applied fixes flowing into that headline. Every widget carries '
         'a "?" whose copy comes from the shared help registry — docs and popovers '
         'cannot drift. Deterministic: the same logs produce this same page, byte for byte.')}"""

# ============================== FINDINGS TABLE ==============================
rows = [
    (CANON_D2, "d2_missing_cache",
     "high", "estimate", "$1,120.10", True),
    ("Frontier model on short completions (avg 92 tokens)", "d1_oversized_model",
     "med", "estimate", "$688.75", False),
    ("System prompt grew 3.1× on the support route", "d3_prompt_bloat",
     "med", "estimate", "$512.40", False),
    ("Cache misses after the Jul 14 deploy", "d2_missing_cache",
     "med", "estimate", "$318.90", False),
    ("Oversized model on classification calls", "d1_oversized_model",
     "low", "estimate", "$164.05", False),
    ("Retry storms — needs per-request logs", "d4_retry_storm",
     "low", "requires logs", "—", False),
]
row_html = []
for title, det, sev, conf, money, expanded in rows:
    badge = ("badge-estimate" if conf == "estimate" else "badge-neutral")
    cls = ' class="expanded"' if expanded else ""
    money_cls = "money" if money != "—" else "money muted"
    row_html.append(f"""              <tr{cls}>
                <td>{icon('i-chevron-down')} {title}</td>
                <td><code class="meta">{det}</code></td>
                <td><span class="sev sev-{sev}">{sev}</span></td>
                <td><span class="badge {badge}">{conf}</span></td>
                <td class="{money_cls}">{money}</td>
                <td><button class="btn btn-quiet">Apply</button></td>
              </tr>""")

findings = f"""{head('Mockup v3 — Findings table + expanded card (R-DESIGN-V3 §1c) — SAMPLE DATA')}
<!-- MOCKUP v3. Findings as a real data table (sortable headers, right-aligned
     tabular money, severity chips, row hover); the card is the EXPANDED state
     of a row, not a separate page. -->
<div class="app">
  {sidebar('Findings')}
  <div>
    {topbar('Findings', 'Pro', 'Data as of <b>2026-07-21 06:30 UTC</b> · audit <code>a7f2…c91</code>')}
    <main class="main">
      <div class="grid">

        <section class="widget w-12">
          <div class="widget-head">
            {icon('i-findings', 'i i-lg')}<h2>11 findings · $2,931.20/mo identified ·
              $1,284.40/mo verified</h2>
            {help_pop("Every finding in your latest audit, sortable by dollars, severity or detector.",
                      "One row per detector per route, priced at the verified rate card and scaled to 30 days.",
                      "Work top-down. Click a row to see its evidence and the exact fix.",
                      "Applying findings")}
          </div>
          <p class="tells">What this tells you: everything the detectors found, ranked
            by monthly dollars. Applied fixes move into the verified figure after the
            next audit covering ≥7 days.</p>
          <table class="ledger">
            <thead><tr>
              <th class="sortable">Finding {icon('i-sort')}</th>
              <th class="sortable">Detector {icon('i-sort')}</th>
              <th class="sortable">Severity {icon('i-sort')}</th>
              <th class="sortable">Confidence {icon('i-sort')}</th>
              <th class="sortable money" aria-sort="descending">Monthly impact {icon('i-sort')}</th>
              <th></th>
            </tr></thead>
            <tbody>
{chr(10).join(row_html)}
            </tbody>
          </table>
          <div class="provenance">Audit <code>a7f2…c91</code> · 1.24M calls · 31 days ·
            rate card v2026-07-17 · 3 of 6 detectors active on connected sources</div>
        </section>

        <article class="widget w-12" aria-labelledby="f1-title">
          <p class="meta muted">Expanded row 1 of 11</p>
          <div style="display:flex; justify-content:space-between; align-items:baseline; gap:var(--s2);">
            <div>
              <h2 id="f1-title" style="margin-bottom: 4px;">{CANON_D2}</h2>
              <span class="sev sev-high">high</span>
              <span class="badge badge-estimate">estimate</span>
              <small class="muted">D2 · missing prompt cache · claude-sonnet-5</small>
            </div>
            <div style="text-align:right;">
              <div class="money money-lg" style="color: var(--waste);">$1,120.10</div>
              <small class="muted">per month</small>
            </div>
          </div>

          <details class="evidence" open>
            <summary>Evidence — 20 sampled calls (counts only)</summary>
            <div>
              <table class="ledger">
                <thead><tr><th>UTC time</th><th>Model</th><th class="money">Prompt tokens</th>
                  <th class="money">Cached</th><th class="money">Billed → as-if-cached</th></tr></thead>
                <tbody>
                  <tr><td>Jul 18 09:14:02</td><td>claude-sonnet-5</td><td class="money">28,412</td>
                    <td class="money">0</td><td class="money">$0.0568 → $0.0071</td></tr>
                  <tr><td>Jul 18 09:14:31</td><td>claude-sonnet-5</td><td class="money">28,412</td>
                    <td class="money">0</td><td class="money">$0.0568 → $0.0071</td></tr>
                  <tr><td>Jul 18 09:15:07</td><td>claude-sonnet-5</td><td class="money">28,395</td>
                    <td class="money">0</td><td class="money">$0.0568 → $0.0071</td></tr>
                </tbody>
              </table>
              <small class="muted">No prompt text is ever stored — token counts,
                timestamps and hashes only.</small>
            </div>
          </details>

          <div style="position:relative; margin-top:var(--s2);">
            <pre class="snippet">"system": [{{"type": "text", "text": SYSTEM_PROMPT,
            "cache_control": {{"type": "ephemeral"}}}}]</pre>
            <button class="btn" style="position:absolute; top:8px; right:8px; padding:4px 10px; font-size:12px;">Copy</button>
          </div>

          <div style="margin-top:var(--s2); display:flex; gap:var(--s1); align-items:center; flex-wrap:wrap;">
            <button class="btn btn-primary">{icon('i-check')} Applied</button>
            <button class="btn">Dismissed</button>
            <button class="btn btn-quiet">Not relevant</button>
            <small class="muted">Applied findings are recomputed on the next audit; the
              verified delta joins your headline.</small>
          </div>
          <div class="provenance">Finding <code>D2-003</code> in audit <code>a7f2…c91</code> ·
            verified amount will be capped at this estimate</div>
        </article>
      </div>
{FOOT % ('MOCKUP v3 — sample data. Delight on this surface: the evidence expander '
         'spring. The card is the expanded state of a table row — one component, three '
         'renderers (table row, expanded card, PDF-static).')}"""

# ============================== FIRST RUN + TOUR ==============================
first = f"""{head('Mockup v3 — First run with guided tour, step 1 (R-DESIGN-V3 §2a) — SAMPLE DATA')}
<!-- MOCKUP v3. Minute one: the same shell, every widget in its designed empty
     state, with tour step 1 of 5 spotlighting the pipeline ribbon. The tour is
     progressive vanilla JS + CSS at V-D4 — no library, no SPA. -->
<div class="app">
  {sidebar('Overview')}
  <div>
    {topbar('Overview', 'Free', 'No data yet — connect a source or upload a log file')}
    <main class="main">

      <div class="steps-bar" aria-label="Getting started, step 1 of 3">
        <span class="cur"><span class="step-n">1</span></span>
        <span class="cur lbl">Bring in your usage — connect a provider or upload a log export</span>
        <span class="step-n">2</span><span class="lbl">We audit it</span>
        <span class="step-n">3</span><span class="lbl">You apply fixes</span>
      </div>

      <div class="grid">

        <section class="w-12" style="position: relative;">
          <div class="widget-head">
            {icon('i-detector', 'i i-lg')}<h2>Your pipeline, right now</h2>
            {help_pop("The five stages of the loop, with live state from your account.",
                      "Stage counts read from your sources, audits, applied findings and alert rules.",
                      "Follow the lit stage — right now that is Input.",
                      "How TokenOps works")}
          </div>
          <p class="tells">What this tells you: the whole loop, and the one step waiting
            on you.</p>
          <div style="position: relative;">
            {EMPTY_RIBBON}
            <!-- tour spotlight sits over the ribbon; popover below it -->
            <div class="tour-spot" style="inset: -6px;"></div>
            <div class="tour-pop" style="left: 0; top: calc(100% + 18px);">
              <div class="step">Step 1 of 5</div>
              <h3>This strip is the whole product</h3>
              <p>Usage comes in, we price and analyse it, you get a ranked report, you
                apply a fix, and alerts watch for the next surprise. Whatever is lit is
                where you are right now.</p>
              <div class="row">
                <div class="tour-dots" aria-hidden="true">
                  <i class="on"></i><i></i><i></i><i></i><i></i>
                </div>
                <span class="spacer"></span>
                <button class="btn btn-quiet">Skip tour</button>
                <button class="btn btn-primary">Next</button>
              </div>
            </div>
          </div>
        </section>

        <section class="widget w-12" aria-labelledby="w1">
          <div class="widget-head">
            {icon('i-savings', 'i i-lg')}<h2 id="w1">Verified savings</h2>
            {help_pop("Money you are no longer spending, proven by a later audit.",
                      "Applied findings are recomputed on the next audit covering at least 7 days.",
                      "Get your first audit in — this fills itself.",
                      "How we verify savings")}
          </div>
          <p class="tells">What this tells you: money you are no longer spending,
            recomputed from your own logs after you apply a fix.</p>
          <div class="empty">
            <p>Your first audit fills this in. Most people are three minutes away —
              connect a provider for daily pulls, or upload a log export for the full
              six-detector audit.</p>
            <a class="btn btn-primary" href="#">{icon('i-source')} Connect OpenAI</a>
            <a class="btn btn-primary" href="#">{icon('i-source')} Connect Anthropic</a>
            <a class="btn" href="#">{icon('i-upload')} Upload a log file</a>
            <a class="btn btn-quiet" href="#">See a sample report first</a>
          </div>
          <div class="provenance">No audits yet · nothing you send us contains prompt
            text — token counts and metadata only</div>
        </section>

        <section class="widget w-6" aria-labelledby="w2">
          <div class="widget-head">{icon('i-trend-up', 'i i-lg')}<h2 id="w2">Spend trend</h2>
            {help_pop("Daily spend across your connected sources.",
                      "Priced from provider-reported token counts at our verified rate card.",
                      "Connect a source — we backfill 30 days immediately.",
                      "Reading your spend chart")}</div>
          <p class="tells">What this tells you: what you are paying now versus the last
            30 days.</p>
          <div class="empty">
            <p>We chart this from your first pull. A connected source backfills 30 days
              immediately, so this is rarely empty for long.</p>
            <a class="btn" href="#">Connect a source</a>
          </div>
          <div class="provenance">Awaiting first pull</div>
        </section>

        <section class="widget w-6" aria-labelledby="w3">
          <div class="widget-head">{icon('i-trend-down', 'i i-lg')}<h2 id="w3">Waste share</h2>
            {help_pop("The share of spend our detectors can account for as avoidable.",
                      "Open findings divided by monthly spend, from your first audit onward.",
                      "Run one audit — then set a target you want to stay under.",
                      "How waste share is calculated")}</div>
          <p class="tells">What this tells you: how much of your spend our detectors can
            account for as avoidable.</p>
          <div class="empty">
            <p>Needs one audit. On connected sources we run three detectors; on uploaded
              request logs, all six.</p>
            <a class="btn btn-quiet" href="#">What each detector finds</a>
          </div>
          <div class="provenance">Awaiting first audit</div>
        </section>

        <section class="widget w-8" aria-labelledby="w4">
          <div class="widget-head">{icon('i-findings', 'i i-lg')}<h2 id="w4">Findings</h2>
            {help_pop("Avoidable costs, ranked by dollars.",
                      "One row per detector per route, priced at the verified rate card.",
                      "Open the sample report to see exactly what a finding looks like.",
                      "Applying findings")}</div>
          <p class="tells">What this tells you: the biggest things worth fixing, ranked
            by dollars.</p>
          <div class="empty">
            <p>Nothing yet. The sample report shows exactly what a finding looks like —
              plain-English title, dollar impact, the evidence behind it, and a fix you
              can paste.</p>
            <a class="btn" href="#">Open the sample report</a>
          </div>
          <div class="provenance">Awaiting first audit</div>
        </section>

        <section class="widget w-4" aria-labelledby="w6">
          <div class="widget-head">{icon('i-clock', 'i i-lg')}<h2 id="w6">Next scheduled audit</h2>
            {help_pop("When your numbers refresh.",
                      "Your plan's cadence, counted from the last completed audit.",
                      "Free covers one full audit of an uploaded file; Pro audits weekly.",
                      "Scheduled audits")}</div>
          <p class="tells">What this tells you: when your numbers refresh.</p>
          <div class="empty">
            <p>Scheduled audits run weekly on Pro. On Free you get one full audit of an
              uploaded log file.</p>
            <a class="btn btn-quiet" href="#">Compare plans</a>
          </div>
          <div class="provenance">Free plan · no schedule</div>
        </section>

        <section class="widget w-4" aria-labelledby="w5">
          <div class="widget-head">{icon('i-source', 'i i-lg')}<h2 id="w5">Sources</h2>
            {help_pop("Your provider connections.",
                      "A connection reads usage counts from the provider's admin API.",
                      "Connect one — it is the fastest path to your first number.",
                      "Managing sources")}</div>
          <p class="tells">What this tells you: whether we are receiving your usage data.</p>
          <div class="empty">
            <p>No sources connected. A connection reads usage counts from your provider's
              admin API — never prompt or completion text.</p>
            <a class="btn btn-primary" href="#">Connect a source</a>
          </div>
          <div class="provenance">0 connections</div>
        </section>

        <section class="widget w-4" aria-labelledby="w7">
          <div class="widget-head">{icon('i-alert', 'i i-lg')}<h2 id="w7">Recent alerts</h2>
            {help_pop("Threshold crossings caught between audits.",
                      "Rules evaluate hourly once you have an audit to compare against.",
                      "Nothing to do yet — alerts arm themselves after your first audit.",
                      "Setting up alerts")}</div>
          <p class="tells">What this tells you: surprises we caught between audits.</p>
          <div class="empty">
            <p>Alerts start watching once you have an audit to compare against.</p>
            <a class="btn btn-quiet" href="#">See what we can alert on</a>
          </div>
          <div class="provenance">No rules armed</div>
        </section>

        <section class="widget w-4" aria-labelledby="w8">
          <div class="widget-head">{icon('i-statement', 'i i-lg')}<h2 id="w8">Savings statement</h2>
            {help_pop("A one-page monthly summary for whoever signs off on the bill.",
                      "Issued at month end from your verified savings.",
                      "See the example to know what your first one will look like.",
                      "Reading your Savings Statement")}</div>
          <p class="tells">What this tells you: the one-page summary you can forward to
            whoever signs off on the bill.</p>
          <div class="empty">
            <p>Your first statement is issued at the end of your first full month.</p>
            <a class="btn btn-quiet" href="#">See an example statement</a>
          </div>
          <div class="provenance">No statements yet</div>
        </section>

      </div>
{FOOT % ('MOCKUP v3 — first-run state with tour step 1 of 5. Delight on this surface: '
         'the pipeline ribbon showing the whole loop with exactly one stage lit. No '
         'number is invented before an audit exists; no shimmer anywhere.')}"""

(OUT / "overview.html").write_text(overview, encoding="utf-8")
(OUT / "findings-table.html").write_text(findings, encoding="utf-8")
(OUT / "first-run-tour.html").write_text(first, encoding="utf-8")
print("wrote:", *(p.name for p in sorted(OUT.iterdir())))
