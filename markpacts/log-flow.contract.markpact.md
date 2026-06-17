# log.read contract (workflow)

Scheme: `log://`

```yaml markpact:contract
apiVersion: urisys.io/v1
kind: UriContract
metadata:
  id: log-flow.contract
  version: 0.1.0
scheme: log
queries:
  - id: log.read
    pattern: log://{target}
    side_effects: false
```

## Role

Read-only log access for workflow steps. Implemented in uri3 via `LogAdapter`
(delegates to `uri3.logs.reader`).

## Workflow output shape

```json
{
  "ok": true,
  "entries": [{"level": "ERROR", "message": "HTTP 502 …"}],
  "count": 1,
  "summary": {"uri": "log://hypervisor?…", "matched": 1, "levels": {"ERROR": 1}}
}
```

Pass to `llm://…/decide` via `context_from: read_logs`.

## Lab gap

`log://` reads via uri3 `LogAdapter` inside `LabCallAdapter`. Set `context.repo_root` or
`URISYS_REPO_ROOT` to the checkout with `output/logs/` when running log flows from the lab container.
