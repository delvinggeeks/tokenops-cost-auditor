# Getting started

Mint a key, make one authenticated call, see it land — the whole loop in
under five minutes. This is the API path; if you'd rather browse every
option first (SDK, connectors, one-off upload), see the
[quickstart](../quickstart.md).

## 1. Mint an ingest key

Sign in, then **Sources → SDK & API → Mint an ingest key** (Pro and Team
plans). It's shown once as a DSN — copy it now:

```
TOKENOPS_COST_AUDITOR_DSN=https://ik_9f2Xw7…@tokenops-cost-auditor.com
```

The key is **write-only**: it can send usage and read nothing back, so a
leaked key can pollute your data but never expose it.

## 2. Put the key where your code can read it

```bash
export TOKENOPS_COST_AUDITOR_KEY=ik_9f2Xw7…   # the token portion of the DSN
```

## 3. Send your first authenticated call

=== "curl"

    ```bash
    curl -X POST https://tokenops-cost-auditor.com/api/v1/ingest \
      -H "Authorization: Bearer $TOKENOPS_COST_AUDITOR_KEY" \
      -H "Content-Type: application/json" \
      -d '{
        "records": [
          {"ts":"2026-07-24T10:00:00Z","provider":"openai","model":"gpt-5.4",
           "prompt_tokens":3084,"completion_tokens":47,"cached_tokens":0}
        ]
      }'
    ```

=== "Python"

    ```python
    import os, requests

    resp = requests.post(
        "https://tokenops-cost-auditor.com/api/v1/ingest",
        headers={"Authorization": f"Bearer {os.environ['TOKENOPS_COST_AUDITOR_KEY']}"},
        json={"records": [
            {"ts": "2026-07-24T10:00:00Z", "provider": "openai", "model": "gpt-5.4",
             "prompt_tokens": 3084, "completion_tokens": 47, "cached_tokens": 0},
        ]},
        timeout=30,
    )
    resp.raise_for_status()
    print(resp.json())   # {"audit_id": "...", "records": 1, "replayed": False}
    ```

A `201` with an `audit_id` means it's accepted and already running the full
six-detector audit.

## 4. See it land

Open your dashboard's **Runs** page — the audit appears the moment the call
above is accepted, and its status moves `queued` → `processing` → `done` in
the background. That's a complete integration: one key, one call, a real
audit.

## Next

- Swap the raw call for the [Python SDK](reference.md#python-sdk) to capture
  every OpenAI/Anthropic call automatically instead of building records by
  hand.
- Walk the full loop programmatically — send, poll, read findings back —
  in [Build your first integration](tutorial.md).
- Every field, every endpoint, every error: the [API reference](reference.md).
