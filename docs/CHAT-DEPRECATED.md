# Deprecation: `chat://` in automation-lab

**Status:** deprecated (2026-06) — use `llm://` + `message://` instead.

## Migration map

| Old | New |
|-----|-----|
| `chat://local/uri/command/execute` | `llm://local/text/query/plan` → `payload_from` → target URI |
| `chat://local/message/command/send` | `message://local/alert/command/send (channel: main)` |
| NL decision on logs | `log://…/query/read` → `llm://…/text/query/decide` |

## Consumer migration (2026-09)

The lab no longer installs or registers `urichat`. The browser and session runner
call the existing `llm://local/text/query/plan` endpoint, check its result, and
send the returned URI and payload through the lab gateway. The browser passes
approval and dry-run context unchanged to both calls. Planning failure stops
execution. Docker and the smoke script use the same endpoint.

The planner is provided by the existing `urillm` pack in the RDP service (or the
local RDP runtime), as in flow 08. This does not add a new planning implementation.
Legacy chat endpoints are no longer supported by the lab. This migration does
not prove that other applications have migrated or authorize deleting the
archived `tellmesh/urichat` repository. Message echo remains an existing
`urimessage` capability; it is not proof of external notification delivery.

## Flows

Lab flows **01–10** no longer declare `chat://` steps. Flow **08** uses `llm://local/text/query/plan`.

External deployments must update their custom chat flows before upgrading.
