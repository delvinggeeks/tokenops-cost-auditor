/* Landing motion, per docs/design/MOTION-SPECS.md C1–C5 (the gate artifact).
   Every effect gates on prefers-reduced-motion and degrades to the final
   state: the markup renders complete and visible before this file runs, so
   a failed script costs decoration, never content. Budget: <15KB (raw). */
(function () {
  "use strict";
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* C5 — tab switch (works regardless of motion preference; the FADE is the
     motion, the swap is function). */
  var tour = document.querySelector("[data-tour-tabs]");
  if (tour) {
    var tabs = tour.querySelectorAll(".tour-tab");
    var panels = tour.querySelectorAll(".tour-panel");
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        tabs.forEach(function (t) { t.setAttribute("aria-selected", String(t === tab)); });
        panels.forEach(function (p) {
          var show = p.getAttribute("data-panel") === tab.getAttribute("data-tab");
          if (show && p.hidden) {
            p.hidden = false;
            if (!reduced) {
              p.style.opacity = "0";
              requestAnimationFrame(function () {
                p.style.transition = "opacity 150ms var(--ease)";
                p.style.opacity = "1";
              });
            }
            countUp(p); /* C4: count-ups fire when a panel becomes visible */
          } else if (!show) {
            p.hidden = true;
            p.style.transition = p.style.opacity = "";
          }
        });
      });
    });
  }

  /* C4 — count-ups. The final figure is IN the markup; animation counts up
     to what is already true, and reduced-motion users simply keep it. */
  var counted = [];
  function countUp(scope) {
    if (reduced) return;
    scope.querySelectorAll("[data-count]").forEach(function (el) {
      if (counted.indexOf(el) !== -1) return; /* once per panel (spec C4) */
      counted.push(el);
      var target = parseFloat(el.getAttribute("data-count"));
      var prefix = el.getAttribute("data-prefix") || "";
      var decimals = (el.getAttribute("data-count").split(".")[1] || "").length;
      var final = el.textContent;
      var t0 = null;
      function step(ts) {
        if (t0 === null) t0 = ts;
        var k = Math.min((ts - t0) / 600, 1);
        k = 1 - Math.pow(1 - k, 3); /* ease-out, 600ms (spec C4) */
        el.textContent = prefix + (target * k).toLocaleString("en-US", {
          minimumFractionDigits: decimals, maximumFractionDigits: decimals
        });
        if (k < 1) requestAnimationFrame(step);
        else el.textContent = final; /* resolve to the exact markup value */
      }
      requestAnimationFrame(step);
    });
  }

  /* C2 — section reveal. Elements are VISIBLE by default; only when motion is
     allowed and the observer exists do we hide-then-reveal. A visitor is
     never left at opacity 0 by a failed script (spec constraint). */
  if (!reduced && "IntersectionObserver" in window) {
    var toReveal = Array.prototype.slice.call(document.querySelectorAll("[data-reveal]"));
    var shown = [];
    function show(el) {
      if (shown.indexOf(el) !== -1) return;
      shown.push(el);
      el.style.opacity = "1";
      el.style.transform = "translateY(0)";
      obs.unobserve(el);
      countUp(el); /* count-ups on first reveal of the visible panel */
    }
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting && e.boundingClientRect.top >= 0) return;
        /* Sections read top-to-bottom, so revealing one reveals everything
           BEFORE it too. Jump scrolls (End key, anchor links) can skip a
           section's intersecting frame entirely — without this invariant a
           reader lands on a page with voids where sections belong. */
        for (var i = 0; i <= toReveal.indexOf(e.target); i++) show(toReveal[i]);
      });
    }, { threshold: 0.15, rootMargin: "600px 0px 600px 0px" });
    toReveal.forEach(function (el) {
      el.style.opacity = "0";
      el.style.transform = "translateY(12px)";
      el.style.transition = "opacity 200ms var(--ease), transform 200ms var(--ease)";
      obs.observe(el);
    });
  } else if (!reduced) {
    countUp(document);
  }

  /* C3 — pipeline stage light-up. Stages render LIT (the sequence is
     decorative, the content is not); with motion allowed we unlight and
     re-light in view order. */
  if (!reduced && "IntersectionObserver" in window) {
    var stages = document.querySelectorAll("[data-stage]");
    var lit = 0;
    stages.forEach(function (s) { s.classList.remove("lit"); });
    var pobs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        pobs.unobserve(e.target);
        var delay = 200 * lit++; /* in sequence, 200ms per stage (spec C3) */
        setTimeout(function () { e.target.classList.add("lit"); }, delay);
      });
    }, { threshold: 0.4 });
    stages.forEach(function (s) { pobs.observe(s); });
  }

  /* C1 — hero tilt, the one 3D moment. Pointer listener on the hero ONLY,
     rAF-throttled; ±6° Y / ±3° X about left center, 120ms catch-up. */
  var shot = document.querySelector("[data-tilt]");
  if (shot && !reduced && window.matchMedia("(pointer: fine)").matches) {
    /* the tilt drives the layered scene when present (C9), the bare image
       otherwise — one handler, both generations of the hero */
    var img = shot.querySelector(".scene-inner") || shot.querySelector("img");
    img.style.transition = "transform 120ms var(--ease)";
    var pending = false, px = 0, py = 0;
    shot.addEventListener("pointermove", function (e) {
      var r = shot.getBoundingClientRect();
      px = (e.clientX - r.left) / r.width - 0.5;
      py = (e.clientY - r.top) / r.height - 0.5;
      if (pending) return;
      pending = true;
      requestAnimationFrame(function () {
        pending = false;
        img.style.transform =
          "perspective(1100px) rotateY(" + (px * 12).toFixed(2) + "deg) rotateX(" +
          (-py * 6).toFixed(2) + "deg)";
      });
    });
    shot.addEventListener("pointerleave", function () {
      img.style.transform = "perspective(1100px) rotateY(0deg) rotateX(0deg)";
    });
  }
})();

/* C6-C8 (MOTION-SPECS): the dollar's journey, the drawn double rule, and the
   one orchestrated hero entrance. All default to the finished state. */
(function () {
  "use strict";
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduced || !("IntersectionObserver" in window)) return;

  /* C8 — hero entrance: rise 8px + fade, 60ms stagger, once on load. */
  var hero = document.querySelector("[data-entrance]");
  if (hero) {
    var kids = Array.prototype.slice.call(hero.children);
    kids.forEach(function (el, i) {
      el.style.opacity = "0";
      el.style.transform = "translateY(8px)";
      el.style.transition = "opacity 200ms var(--ease), transform 200ms var(--ease)";
      setTimeout(function () {
        el.style.opacity = "1";
        el.style.transform = "translateY(0)";
      }, 40 + i * 60);
    });
  }

  /* C6 — the flow line draws through the five stages, once, on view. */
  var ink = document.querySelector(".pipe-line-ink");
  if (ink) {
    ink.style.strokeDashoffset = "1000";
    new IntersectionObserver(function (es, obs) {
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        obs.disconnect();
        ink.style.transition = "stroke-dashoffset 900ms var(--ease)";
        ink.style.strokeDashoffset = "0";
        ink.closest(".pipe-wrap").classList.add("pipe-go"); /* C10 pulse */
      });
    }, { threshold: 0.3 }).observe(ink.closest(".pipe-wrap"));
  }

  /* C7 — the accountant's double rule draws under the self-audit figure. */
  var rule = document.querySelector(".proof-rule");
  if (rule) {
    var strokes = rule.querySelectorAll("path");
    strokes.forEach(function (s) { s.style.strokeDashoffset = "100"; });
    new IntersectionObserver(function (es, obs) {
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        obs.disconnect();
        strokes.forEach(function (s, i) {
          s.style.transition = "stroke-dashoffset 400ms var(--ease) " + i * 120 + "ms";
          s.style.strokeDashoffset = "0";
        });
      });
    }, { threshold: 0.4 }).observe(rule.closest(".land-proof"));
  }
})();
