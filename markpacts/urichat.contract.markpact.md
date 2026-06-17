# urichat contract (MVP)

Scheme: `chat://`

```yaml markpact:contract
apiVersion: urisys.io/v1
kind: UriContract
metadata:
  id: urichat.contract
  version: 0.1.0
scheme: chat
commands:
  - id: chat.message.send
    pattern: chat://local/message/command/send
    side_effects: true
    requires_approval: true
  - id: chat.uri.execute
    pattern: chat://local/uri/command/execute
    side_effects: true
    requires_approval: true
```

## Routes

```txt
chat://local/message/command/send
chat://local/uri/command/execute
```

## Role

Map natural language / transcript → URI envelope → forward to urisys (`/uri/call`).

Does **not** replace `llm://` planning — it is a thin bridge for voice/UI commands.

## Example

```json
{
  "uri": "chat://local/uri/command/execute",
  "payload": {
    "transcript": "kliknij OK",
    "approved": true,
    "dry_run": true
  }
}
```
