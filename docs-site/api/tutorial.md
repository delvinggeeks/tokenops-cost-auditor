# Build your first integration

A runnable, end-to-end walk-through of the programmatic loop: **send usage
→ poll status → read findings** — no browser, no dashboard clicking,
everything through the API. Have two credentials ready first:

1. An **ingest key** (`ik_…`) — **Sources → SDK & API → Mint an ingest key**.
2. A **read token** (`rt_…`) with both `read:audits` and `read:findings`
   scopes — **Developer → API tokens**.

Set both as environment variables before you start:

```bash
export TOKENOPS_COST_AUDITOR_KEY=ik_…      # write-only: sends usage
export TOKENOPS_COST_AUDITOR_TOKEN=rt_…    # read-only: reads audits + findings
```

## 1. Send usage

`POST /api/v1/ingest` accepts a batch of per-call usage records and starts
an audit immediately. See [Send usage](reference.md#send-usage) for the
full field table.

```python
import os, time, requests

BASE = "https://tokenops-cost-auditor.com/api/v1"
INGEST_KEY = os.environ["TOKENOPS_COST_AUDITOR_KEY"]
READ_TOKEN = os.environ["TOKENOPS_COST_AUDITOR_TOKEN"]

resp = requests.post(
    f"{BASE}/ingest",
    headers={"Authorization": f"Bearer {INGEST_KEY}"},
    json={"records": [
        {"ts": "2026-07-24T10:00:00Z", "provider": "openai", "model": "gpt-5.4",
         "prompt_tokens": 3084, "completion_tokens": 47, "cached_tokens": 0},
        {"ts": "2026-07-24T10:05:00Z", "provider": "openai", "model": "gpt-5.4",
         "prompt_tokens": 3084, "completion_tokens": 52, "cached_tokens": 3084},
    ]},
    timeout=30,
)
resp.raise_for_status()
audit_id = resp.json()["audit_id"]
print("audit_id:", audit_id)
```

## 2. Poll status

An ingest key is **write-only** — it can't read anything back, so polling
uses the read token instead. There's no single-audit status route for read
tokens; [List audits](reference.md#list-audits) returns every recent audit's
`status`, so find yours by id:

```python
def wait_for_audit(audit_id, timeout_s=120, interval_s=3):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = requests.get(
            f"{BASE}/audits",
            headers={"Authorization": f"Bearer {READ_TOKEN}"},
            timeout=30,
        )
        r.raise_for_status()
        match = next((a for a in r.json()["audits"] if a["id"] == audit_id), None)
        if match and match["status"] in ("done", "failed"):
            return match
        time.sleep(interval_s)
    raise TimeoutError(f"{audit_id} still not done after {timeout_s}s")

audit = wait_for_audit(audit_id)
print("status:", audit["status"], "· findings:", audit["findings"])
```

## 3. Read findings

Once `status` is `done`, [List findings](reference.md#list-findings) returns
every finding for that audit, ranked by monthly dollar impact:

```python
if audit["status"] == "done":
    r = requests.get(
        f"{BASE}/audits/{audit_id}/findings",
        headers={"Authorization": f"Bearer {READ_TOKEN}"},
        timeout=30,
    )
    r.raise_for_status()
    for f in r.json()["findings"]:
        print(f"{f['detector']:24} {f['severity']:8} "
              f"${f['monthly_cost_impact_usd']:.2f}/mo — {f['fix']}")
```

## The whole script

Paste steps 1–3 together (or run each `curl` below in sequence) and you have
a complete, working integration:

=== "curl"

    ```bash
    # 1. send usage
    AUDIT_ID=$(curl -s -X POST https://tokenops-cost-auditor.com/api/v1/ingest \
      -H "Authorization: Bearer $TOKENOPS_COST_AUDITOR_KEY" \
      -H "Content-Type: application/json" \
      -d '{"records":[{"ts":"2026-07-24T10:00:00Z","provider":"openai",
           "model":"gpt-5.4","prompt_tokens":3084,"completion_tokens":47,
           "cached_tokens":0}]}' | python3 -c "import sys,json;print(json.load(sys.stdin)['audit_id'])")

    # 2. poll status (repeat until status is "done")
    curl -s -H "Authorization: Bearer $TOKENOPS_COST_AUDITOR_TOKEN" \
      https://tokenops-cost-auditor.com/api/v1/audits | \
      python3 -c "import sys,json;a=[a for a in json.load(sys.stdin)['audits'] if a['id']=='$AUDIT_ID'];print(a[0]['status'] if a else 'not found yet')"

    # 3. read findings
    curl -s -H "Authorization: Bearer $TOKENOPS_COST_AUDITOR_TOKEN" \
      "https://tokenops-cost-auditor.com/api/v1/audits/$AUDIT_ID/findings"
    ```

=== "Python"

    ```python
    import os, time, requests

    BASE = "https://tokenops-cost-auditor.com/api/v1"
    INGEST_KEY = os.environ["TOKENOPS_COST_AUDITOR_KEY"]
    READ_TOKEN = os.environ["TOKENOPS_COST_AUDITOR_TOKEN"]

    resp = requests.post(
        f"{BASE}/ingest",
        headers={"Authorization": f"Bearer {INGEST_KEY}"},
        json={"records": [
            {"ts": "2026-07-24T10:00:00Z", "provider": "openai", "model": "gpt-5.4",
             "prompt_tokens": 3084, "completion_tokens": 47, "cached_tokens": 0},
        ]},
        timeout=30,
    )
    resp.raise_for_status()
    audit_id = resp.json()["audit_id"]

    deadline = time.monotonic() + 120
    audit = None
    while time.monotonic() < deadline:
        r = requests.get(f"{BASE}/audits",
                          headers={"Authorization": f"Bearer {READ_TOKEN}"}, timeout=30)
        r.raise_for_status()
        match = next((a for a in r.json()["audits"] if a["id"] == audit_id), None)
        if match and match["status"] in ("done", "failed"):
            audit = match
            break
        time.sleep(3)

    if audit and audit["status"] == "done":
        r = requests.get(f"{BASE}/audits/{audit_id}/findings",
                          headers={"Authorization": f"Bearer {READ_TOKEN}"}, timeout=30)
        r.raise_for_status()
        for f in r.json()["findings"]:
            print(f"{f['detector']:24} {f['severity']:8} "
                  f"${f['monthly_cost_impact_usd']:.2f}/mo — {f['fix']}")
    ```

## What you just built

A script that sends real usage, waits for the audit engine to finish, and
prints back dollar-ranked findings — the same three calls a CI job,
scheduled script, or internal tool would make to watch spend continuously.
Two records is enough to prove the loop; point it at your real usage stream
next, or [instrument automatically with the SDK](reference.md#python-sdk)
instead of building records by hand.
