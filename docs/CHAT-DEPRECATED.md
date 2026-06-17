# Deprecation: `chat://` in automation-lab

**Status:** deprecated (2026-06) — use `llm://` + `message://` instead.

## Migration map

| Old | New |
|-----|-----|
| `chat://local/uri/command/execute` | `llm://local/text/query/plan` → `payload_from` → target URI |
| `chat://local/message/command/send` | `message://local/human/command/notify` |
| NL decision on logs | `log://…/query/read` → `llm://…/text/query/decide` |

## Still present (shim)

- `urisys-automation-lab/server/lab_uri_adapter.py` — forwards legacy `chat://` execute steps
- `tellmesh/urichat/` — deprecated phrase-map pack (pip `urichat>=0.1.0`)
- Markpacts: `urichat/markpacts/urichat.contract.markpact.md`, references in `uristt`

## Flows

Lab flows **01–10** no longer declare `chat://` steps. Flow **08** uses `llm://local/text/query/plan`.

Removal target: next major lab release after all STT/WebRTC demos migrate to `llm://`.
