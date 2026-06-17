"""Execute compact *.uri.flow.yaml via uri2flow (expand) + uri3 (graph run)."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import yaml

try:
    from uri2flow import expand_flow
    from uri3.graph import ExecutionContext, load_workflow_graph, topological_sort
    from uri3.graph.adapters.registry import ADAPTERS
    from uri3.graph.step_runner import run_workflow_node
except ImportError as exc:  # pragma: no cover - optional until pip install uri2flow
    expand_flow = None  # type: ignore[assignment,misc]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

from lab_uri_adapter import LabCallAdapter


def _require_uri_stack() -> None:
    if _IMPORT_ERROR is not None:
        raise ImportError(
            "flow execution requires uri2flow and uri3 (pip install 'uri2flow>=0.1.2')"
        ) from _IMPORT_ERROR


def _execution_root(flow_path: Path, ctx: dict[str, Any]) -> Path:
    if ctx.get("repo_root"):
        return Path(str(ctx["repo_root"]))
    env_root = os.environ.get("URISYS_REPO_ROOT")
    if env_root:
        return Path(env_root)
    resolved = flow_path.resolve()
    if resolved.parent.name == "flows":
        return resolved.parents[1]
    return resolved.parent


def _load_defaults(flow_path: str | Path) -> dict[str, Any]:
    data = yaml.safe_load(Path(flow_path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {}
    defaults = data.get("defaults") or {}
    return dict(defaults) if isinstance(defaults, dict) else {}


@contextmanager
def _lab_adapter_session():
    adapter = LabCallAdapter()
    ADAPTERS.insert(0, adapter)
    try:
        yield adapter
    finally:
        ADAPTERS.pop(0)


def plan_flow(flow_path: str | Path) -> dict[str, Any]:
    _require_uri_stack()
    path = Path(flow_path)
    expanded = expand_flow(path)
    workflow = load_workflow_graph(expanded)
    order = topological_sort(workflow)
    steps = [workflow.nodes[node_id] for node_id in order]
    return {
        "flow_id": workflow.id,
        "description": workflow.description,
        "defaults": _load_defaults(path),
        "flow_path": str(path),
        "graph": expanded,
        "steps": steps,
        "workflow": workflow,
    }


def _legacy_step(node: Any, step: Any, payload: dict[str, Any], step_ctx: dict[str, Any]) -> dict[str, Any]:
    raw_response = (step.result or {}).get("response")
    if not isinstance(raw_response, dict):
        raw_response = step.result if isinstance(step.result, dict) else {"ok": step.ok, "result": step.result}
    return {
        "id": node.id,
        "uri": node.uri,
        "operation": node.operation,
        "kind": node.kind,
        "depends_on": list(node.depends_on or []),
        "payload": payload,
        "context": {
            k: step_ctx[k]
            for k in ("approved", "allow_real", "dry_run", "display", "xauthority")
            if k in step_ctx
        },
        "ok": step.ok,
        "status": step.status,
        "response": raw_response,
        "error": step.error,
    }


def run_flow_file(
    flow_path: str | Path,
    *,
    call_uri: Callable[[str, dict[str, Any], dict[str, Any]], dict[str, Any]],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _require_uri_stack()
    plan = plan_flow(flow_path)
    workflow = plan["workflow"]

    ctx = dict(context or {})
    defaults = plan.get("defaults") or {}
    if defaults.get("approved") is not None:
        ctx.setdefault("approved", bool(defaults.get("approved")))
    if defaults.get("dry_run") is not None and "dry_run" not in ctx:
        ctx["dry_run"] = bool(defaults.get("dry_run"))
    ctx.setdefault("approved", True)

    execution = ExecutionContext(
        workflow_id=str(plan["flow_id"]),
        run_id=str(uuid4()),
        root=_execution_root(Path(plan["flow_path"]), ctx),
        approve_commands=bool(ctx.get("approved", True)),
        dry_run=bool(ctx.get("dry_run", False)),
    )
    execution.adapter_state["call_uri"] = call_uri
    execution.adapter_state["lab_context"] = ctx

    results: list[dict[str, Any]] = []
    completed: dict[str, Any] = {}
    pending_approval: list[str] = []

    with _lab_adapter_session():
        for node_id in topological_sort(workflow):
            node = workflow.nodes[node_id]
            payload = dict(node.payload or {})
            step_ctx = dict(ctx)
            if str(node.uri).startswith("chat://") and "execute" in str(node.uri):
                payload.setdefault("approved", True)
                payload["dry_run"] = False
                step_ctx["dry_run"] = False
                step_ctx["allow_real"] = True

            step, should_continue = run_workflow_node(
                node,
                workflow_id=str(plan["flow_id"]),
                approve=bool(ctx.get("approved", True)),
                dry_run=bool(ctx.get("dry_run", False)),
                context=execution,
                completed=completed,
                pending_approval=pending_approval,
            )
            results.append(_legacy_step(node, step, payload, step_ctx))
            if not should_continue:
                break

    return {
        "flow_id": plan["flow_id"],
        "flow_path": plan["flow_path"],
        "description": plan["description"],
        "graph": plan["graph"],
        "ok": all(step["ok"] for step in results) and bool(results),
        "steps": results,
        "pending_approval": pending_approval,
    }
