# llm.text.decide contract (MVP)

Scheme: `llm://`

```yaml markpact:contract
apiVersion: urisys.io/v1
kind: UriContract
metadata:
  id: urillm-decide.contract
  version: 0.1.0
scheme: llm
commands:
  - id: llm.text.decide
    pattern: llm://{target}/text/query/decide
    side_effects: false
    requires_approval: false
queries:
  - id: llm.vision.analyze
    pattern: llm://{target}/vision/query/analyze
    side_effects: false
  - id: llm.text.plan
    pattern: llm://{target}/text/query/plan
    side_effects: false
```

## Routes

```txt
llm://local/text/query/decide
llm://local/vision/query/analyze
```

## Role

**NL judge** for workflow branching. Consumes structured context (typically `log://` output)
and returns `{ok, decision, reason}` for `if:` conditions.

Not a URI forwarder — use `rdp://` / `kvm://` / `hypervisor://` for actions.

## Example

```json
{
  "uri": "llm://local/text/query/decide",
  "payload": {
    "question": "Czy te logi wskazują na problem z forwardem do urirdp?",
    "context_from": "read_logs",
    "expect": "boolean"
  }
}
```

## Response

```json
{
  "ok": true,
  "decision": "retry",
  "reason": "ERROR + 502 in log entries",
  "confidence": 0.82,
  "model": "mock-decide"
}
```

## Host placement

| Runtime | Handler |
|---------|---------|
| uri3 workflow (host) | `uri3.graph.adapters.llm_adapter` |
| urirdp / lab forward | `urirdp_llm.handlers.decide` |

LLM API keys remain on host / urirdp profile (`.env`, `litellm` driver).
