"""Lab HTTP adapter for uri3 — routes workflow steps through automation-lab call_uri."""

from __future__ import annotations

from typing import Any, Callable
from urllib.parse import urlparse

from uri3.graph.execution_models import ExecutionContext
from uri3.graph.models import GraphNode

try:
    from uri3.graph.payload_context import merge_payload_from, resolve_step_payload
except ImportError:  # pragma: no cover
    resolve_step_payload = None  # type: ignore[assignment,misc]
    merge_payload_from = None  # type: ignore[assignment,misc]

# Schemes handled locally or forwarded to urirdp via lab gateway.
LAB_SCHEMES = frozenset(
    {
        "shell",
        "browser",
        "kvm",
        "him",
        "ocr",
        "llm",
        "rdp",
        "env",
        "stt",
        "chat",
        "message",
        "webrtc",
        "http",
        "https",
        "log",
    }
)


def step_ok(response: dict[str, Any], *, allow_real: bool) -> bool:
    if not bool(response.get("ok")):
        return False
    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    if isinstance(result, dict):
        if result.get("ok") is False:
            return False
        exit_code = result.get("exit_code")
        if exit_code is not None and exit_code != 0:
            return False
        if allow_real and result.get("mode") == "dry_run":
            return False
    return True


class LabCallAdapter:
    schemes = LAB_SCHEMES

    def execute(self, node: GraphNode, context: ExecutionContext) -> dict[str, Any]:
        call_uri: Callable[[str, dict[str, Any], dict[str, Any]], dict[str, Any]] | None = (
            context.adapter_state.get("call_uri")
        )
        if call_uri is None:
            return {"ok": False, "error": "lab call_uri not configured"}

        base_ctx = dict(context.adapter_state.get("lab_context") or {})
        uri = str(node.uri)
        payload = dict(node.payload or {})
        if resolve_step_payload is not None:
            payload = resolve_step_payload(payload, context)
        resolved_uri = str(payload.pop("_resolved_uri", "") or uri)
        step_ctx = dict(base_ctx)

        if resolved_uri.startswith("chat://") and "execute" in resolved_uri:
            payload.setdefault("approved", True)
            payload["dry_run"] = False
            step_ctx["dry_run"] = False
            step_ctx["allow_real"] = True

        if resolved_uri.startswith("message://"):
            payload.setdefault("approved", True)

        if context.dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "uri": resolved_uri,
                "operation": node.operation,
                "payload": payload,
            }

        scheme = urlparse(resolved_uri).scheme
        if scheme == "log":
            return self._execute_log(node, context, resolved_uri, payload)

        try:
            response = call_uri(resolved_uri, payload, step_ctx)
        except Exception as exc:
            response = {"ok": False, "uri": resolved_uri, "error": str(exc)}

        ok = step_ok(response, allow_real=bool(step_ctx.get("allow_real")))
        return {
            "ok": ok,
            "uri": resolved_uri,
            "operation": node.operation,
            "response": response,
        }

    def _execute_log(
        self,
        node: GraphNode,
        context: ExecutionContext,
        uri: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            from uri3.graph.adapters.log_adapter import LogAdapter
        except ImportError as exc:
            return {"ok": False, "uri": uri, "error": f"log adapter unavailable: {exc}"}

        log_node = GraphNode(
            id=node.id,
            uri=uri,
            operation=node.operation,
            kind=node.kind,
            payload=payload,
            depends_on=list(node.depends_on or []),
            condition=node.condition,
        )
        result = LogAdapter().execute(log_node, context)
        return {"ok": bool(result.get("ok")), "uri": uri, "operation": node.operation, **result}
