"""Detector display copy — the SINGLE SOURCE of the plain-English finding copy,
at the SERVICES layer so BOTH the in-app findings (web/help.py) AND the downloadable
report (services/report) render the SAME words (ROADMAP §3 #3 — report plain-English
parity). Static text only, no thresholds/settings (those interpolate in web/help.py).
Moved verbatim from web/help_registry.yaml; the engine stays network/LLM-free (T-NFR-01).
"""

from __future__ import annotations

DETECTOR_COPY: dict[str, dict[str, str]] = {
    "d1_oversized_model": {
        "plain": "You're using a top-tier model for work a cheaper one handles",
        "summary": "Everyday requests are running on your most expensive model, "
        "when a smaller, cheaper one would handle them just as well. "
        "You're paying premium rates for routine work.",
        "technical": "D1 oversized model",
        "why": "Flagged when a frontier model's average completion is under "
        "{d1_short_completion_t} tokens — short answers rarely need the "
        "largest model. Savings are priced at the suggested model's own "
        "rate card.",
        "fix": "Route this traffic to the suggested model and keep the frontier "
        "model for genuinely long generations.",
        "verify": "Your next audit prices the same routes at the new model; the "
        "difference lands in verified savings.",
        "methodology_url": "/methodology/#d1-oversized-model",
    },
    "d2_missing_cache": {
        "plain": "You're paying full price for prompts you send again and again",
        "summary": "Some requests repeat the same large block of text at the start "
        "every time. Your provider can store that block and charge a "
        "fraction to reuse it — but that caching isn't switched on, so "
        "you pay full price for the same text on every call.",
        "technical": "D2 missing prompt cache",
        "why": "Flagged when the same prompt prefix repeats at least "
        "{d2_cache_min_repeats} times at {d2_cache_min_prompt_tokens} "
        "tokens or more without cache reads. Savings are haircut by "
        "{d2_suffix_haircut} for prefix drift.",
        "fix": "Mark the stable prefix with your provider's cache control so "
        "repeat calls read it instead of re-sending it.",
        "verify": "Your next audit sees cache reads on those calls, and the "
        "finding shrinks or disappears.",
        "methodology_url": "/methodology/#d2-missing-cache",
    },
    "d3_prompt_bloat": {
        "plain": "One route's prompts are far larger than the rest",
        "summary": "One part of your app sends much bigger prompts than everywhere "
        "else — usually old context or examples that pile up and never "
        "get trimmed. You pay for every extra word, on every call.",
        "technical": "D3 prompt bloat",
        "why": "Flagged when a route's average prompt exceeds {d3_bloat_mult}x the "
        "median for the same model. The excess is priced at the rate those "
        "tokens were actually billed.",
        "fix": "Trim the system prompt or context growth on that route — usually "
        "accumulated examples or unpruned history.",
        "verify": "Your next audit measures the smaller prompts; the excess "
        "disappears from your waste share.",
        "methodology_url": "/methodology/#d3-prompt-bloat",
    },
    "d4_retry_storm": {
        "plain": "The same request is being sent over and over in bursts",
        "summary": "The same request is being sent many times within a few seconds — "
        "usually an automatic retry with no limit. Every attempt is "
        "billed, so one burst can multiply the cost.",
        "technical": "D4 retry storm",
        "why": "Flagged when {d4_dup_min} or more identical requests land within "
        "{d4_window_s} seconds. Requires per-request logs — provider usage "
        "APIs report daily totals only.",
        "fix": "Add backoff and a retry ceiling on that client, and make the retry "
        "condition narrower.",
        "verify": "Your next audit shows the burst gone; the duplicate calls stop appearing.",
        "methodology_url": "/methodology/#d4-retry-storm",
    },
    "d5_unbounded_max_tokens": {
        "plain": "Your output limits are set far above what you actually use",
        "summary": "Your requests allow far longer answers than you ever "
        "actually get back. Most providers bill for the words "
        "actually generated, so this rarely costs money today — "
        "but it leaves the door open to a runaway, very "
        "expensive response.",
        "technical": "D5 unbounded max_tokens",
        "why": "Flagged when the declared max_tokens is {d5_max_ratio}x or "
        "more your 95th-percentile completion. Informational: most "
        "providers bill actual output, so this is a risk signal, not "
        "a bill.",
        "fix": "Set max_tokens close to your real p95 output, with headroom "
        "for the longest legitimate answer.",
        "verify": "Nothing changes on your bill — this protects you from a runaway generation.",
        "methodology_url": "/methodology/#d5-unbounded-max-tokens",
    },
    "d6_chatty_loop": {
        "plain": "An agent loop is making many tiny calls where fewer would do",
        "summary": "An automated loop is firing lots of tiny requests back-to-back. "
        "Doing the same work in fewer, larger calls costs less — every "
        "call carries fixed overhead you're paying again and again.",
        "technical": "D6 chatty agent loop",
        "why": "Flagged when {d6_loop_min} or more calls under "
        "{d6_small_completion_t} completion tokens run inside "
        "{d6_run_window_s} seconds. Savings assume batching into groups of "
        "{d6_batch_sz}.",
        "fix": "Batch the loop's work into fewer calls, or cache the repeated "
        "context between iterations.",
        "verify": "Your next audit sees fewer, larger calls on that route and prices "
        "the difference.",
        "methodology_url": "/methodology/#d6-chatty-loop",
    },
    "d8_spend_concentration": {
        "plain": "One route is eating most of your spend",
        "summary": "A single part of your app accounts for most of what you "
        "spend on LLM calls. It's not waste on its own — but it's "
        "where optimizing pays off the most, because the fixes "
        "that touch this route move the most money.",
        "technical": "D8 spend concentration",
        "why": "Flagged when one route is at least "
        "{d8_concentration_min_share_pct} of total audited spend, "
        "across two or more named routes. Informational — no dollar "
        "saving is claimed.",
        "fix": "Start your optimization here — apply the caching, "
        "model-sizing and prompt fixes on this route first, since it "
        "carries the most dollars.",
        "verify": "As you optimize this route, its share of spend drops on "
        "your next audit and your total spend falls.",
        "methodology_url": "/methodology/#d8-spend-concentration",
    },
    "d9_ineffective_cache": {
        "plain": "Your prompt caching is costing more than it saves",
        "summary": "You've turned on prompt caching, but it isn't paying off — "
        "the calls rarely reuse the cached text, so you keep paying "
        "the higher write price without getting the read discount "
        "back. Right now the caching is a net cost, not a saving.",
        "technical": "D9 ineffective cache",
        "why": "Flagged when a route's cache-write premium exceeds its "
        "cache-read savings, over at least {d9_min_cache_write_tokens} "
        "cache-write tokens. Computed from the actual billed "
        "cache_write and cache_read token counts, so it is "
        "conservative, not an estimate.",
        "fix": "Make the cached prefix stable and ensure repeat calls reuse it "
        "within the cache TTL — or stop caching this route. Fewer "
        "writes, more reads.",
        "verify": "Your next audit shows more cache reads (or fewer writes) on "
        "this route, and its net cost flips to a saving.",
        "methodology_url": "/methodology/#d9-ineffective-cache",
    },
    "d10_spend_anomaly": {
        "plain": "One day's spend spiked far above your normal",
        "summary": "On at least one day, your LLM spend jumped well above what "
        "you normally spend in a day. A spike like that is usually a "
        "runaway job, a data backfill, a load test, or a job sent to "
        "the wrong, pricier model — sometimes intended, sometimes not. "
        "We flag it so you can check whether that money was meant to "
        "be spent, because these events tend to repeat.",
        "technical": "D10 spend anomaly",
        "why": "Flagged when a day's spend is a robust statistical outlier — at "
        "least {d10_z_threshold} MADs above your median day AND at least "
        "{d10_spike_mult}x that median — measured over at least "
        "{d10_min_days} days. Robust statistics (median + MAD) so a spike "
        "cannot hide itself; both tests are scale-free, so a long audit "
        "never dilutes a real spike out of range. Compared against your "
        "own typical day. Informational — no dollar saving is claimed.",
        "fix": "Confirm the spike was intended. If it was a runaway loop, a retry "
        "storm, or a job sent to the wrong (pricier) model, fix that job "
        "so it can't recur — and check the same day's pattern findings, "
        "which price the recoverable part.",
        "verify": "Your next audit shows that day's spend back near your typical "
        "range, with no unexplained spike.",
        "methodology_url": "/methodology/#d10-spend-anomaly",
    },
}


def entry(key: str) -> dict[str, str] | None:
    """The full copy block for a detector key, or None if unknown."""
    return DETECTOR_COPY.get(key)


def plain(key: str) -> str:
    """Headline-depth phrasing (no thresholds). Falls back to the key if unknown."""
    e = DETECTOR_COPY.get(key)
    return e["plain"] if e else key


def summary(key: str) -> str:
    """Plain-English 'what this means' that leads a finding wherever it is read."""
    e = DETECTOR_COPY.get(key)
    return e["summary"] if e else ""
