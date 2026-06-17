# message.alert contract (MVP)

Scheme: `message://`

```yaml markpact:contract
apiVersion: urisys.io/v1
kind: UriContract
metadata:
  id: urimessage.contract
  version: 0.1.0
scheme: message
commands:
  - id: message.alert.send
    pattern: message://local/alert/command/send
    side_effects: true
    requires_approval: true
```

## Role

Human-facing notification / escalation — **not** LLM inference.  
Replaces `chat://local/message/command/send` in NL-log-decision flows.

## Example

```json
{
  "uri": "message://local/alert/command/send",
  "payload": {
    "text": "W logach wykryto krytyczny błąd — wymaga interwencji",
    "severity": "critical",
    "approved": true
  }
}
```
