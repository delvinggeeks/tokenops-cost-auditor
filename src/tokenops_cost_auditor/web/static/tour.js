/* Guided tour (PLAN-V15 V-D4g; R-DESIGN-V3 §2a).
   Progressive enhancement: without JS the popover still renders step 1 with a
   working Skip (server-side POST). No library, no framework, no build step.
   Dismissal persists server-side; "Replay tour" clears it. */
(function () {
  "use strict";
  var pop = document.getElementById("tour");
  if (!pop) return;

  var STEPS = [
    { sel: "#pipeline-ribbon", title: "This strip is the whole product",
      body: "Usage comes in, we price and analyse it, you get a ranked report, you apply a fix, and alerts watch for the next surprise. Whatever is lit is where you are right now." },
    { sel: "#w-savings", title: "The only number your CFO needs",
      body: "Money you are no longer spending, recomputed from your own logs after a fix ships. Estimates sit beside it, clearly labelled — they never inflate this figure." },
    { sel: "#w-top_findings", title: "Work top-down, in dollars",
      body: "Findings are ranked by monthly impact, not severity labels. Open one for the evidence and a fix you can paste, then mark it Applied when it ships." },
    { sel: "#w-sources", title: "Where your data comes from",
      body: "A connected source pulls usage counts daily — never prompt text. Upload a request log instead when you want all six detectors." },
    { sel: "#w-next_audit", title: "It keeps checking without you",
      body: "Audits run weekly. Anything you applied gets re-measured, and alerts watch the gaps in between." }
  ];

  var i = 0;
  var spot = document.createElement("div");
  spot.className = "tour-spot";
  document.body.appendChild(spot);

  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function place() {
    var step = STEPS[i];
    var el = document.querySelector(step.sel);
    document.getElementById("tour-n").textContent = String(i + 1);
    document.getElementById("tour-title").textContent = step.title;
    document.getElementById("tour-body").textContent = step.body;
    pop.querySelectorAll(".tour-dots i").forEach(function (d, n) {
      d.classList.toggle("on", n === i);
    });
    if (!el) { spot.style.display = "none"; return; }
    var r = el.getBoundingClientRect();
    spot.style.display = "block";
    spot.style.position = "absolute";
    spot.style.left = (r.left + window.scrollX - 6) + "px";
    spot.style.top = (r.top + window.scrollY - 6) + "px";
    spot.style.width = (r.width + 12) + "px";
    spot.style.height = (r.height + 12) + "px";
    el.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
    /* Design audit F8: the popover sits NEXT TO what it spotlights — a guide
       pointing from the far corner makes the reader do the finding. Below the
       target, clamped to the viewport; small screens keep the fixed corner
       (the popover would cover the target anyway). */
    if (window.innerWidth >= 720) {
      var w = pop.offsetWidth || 340;
      var left = Math.min(Math.max(r.left + window.scrollX, 16),
                          window.scrollX + window.innerWidth - w - 16);
      pop.style.position = "absolute";
      pop.style.bottom = "auto";
      pop.style.left = left + "px";
      pop.style.top = (r.bottom + window.scrollY + 14) + "px";
      /* the guide itself must never sit half-cut at the fold */
      pop.scrollIntoView({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
    }
  }

  document.getElementById("tour-next").addEventListener("click", function () {
    i += 1;
    if (i >= STEPS.length) {
      // last step: finishing IS dismissing
      var skip = pop.querySelector("[hx-post='/tour/dismiss']");
      if (skip) { skip.click(); } else { pop.remove(); }
      spot.remove();
      return;
    }
    if (i === STEPS.length - 1) {
      document.getElementById("tour-next").textContent = "Done";
    }
    place();
  });

  pop.addEventListener("htmx:afterRequest", function () { spot.remove(); });
  window.addEventListener("resize", place);
  place();
})();
