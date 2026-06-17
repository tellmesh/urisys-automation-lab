from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

# Simple phrase → URI map for voice demos.
_PHRASE_MAP: list[tuple[str, str, dict[str, Any]]] = [
    ("kliknij ok", "kvm://local/task/command/click-text", {"text": "OK"}),
    ("otwórz przeglądark", "browser://chrome/page/open", {"url": "http://localhost:8101/health"}),
    ("zrób screenshot", "kvm://local/monitor/primary/query/screenshot", {}),
    ("status rdp", "rdp://local/display/query/status", {}),
]


def _match_transcript(text: str) -> tuple[str, dict[str, Any]]:
    lowered = (text or "").lower().strip()
    for phrase, uri, payload in _PHRASE_MAP:
        if phrase in lowered:
            return uri, dict(payload)
    return "kvm://local/task/command/click-text", {"text": "OK"}


def _forward_uri(uri: str, payload: dict[str, Any], context: dict[str, Any], base_url: str) -> dict[str, Any]:
    body = json.dumps({"uri": uri, "payload": payload, "context": context}).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/uri/call",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return {"ok": False, "error": str(exc), "uri": uri, "forwarded_to": base_url}


def message_send(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("text") or "")
    return {"ok": True, "text": text, "channel": payload.get("channel", "main"), "echo": True}


def uri_execute(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    cfg = (context.get("config") or {}).get("chat") or {}
    base_url = cfg.get("urisys_base_url") or context.get("urisys_base_url") or "http://127.0.0.1:8795"

    uri = str(payload.get("uri") or "")
    inner_payload = dict(payload.get("payload") or {})
    approved = bool(payload.get("approved", context.get("approved")))
    dry_run = bool(payload.get("dry_run", context.get("dry_run")))

    transcript = payload.get("transcript") or payload.get("text")
    if transcript and not uri:
        uri, inner_payload = _match_transcript(str(transcript))

    if not uri:
        return {"ok": False, "error": "payload.uri or payload.transcript required"}

    forward_context = {
        "approved": approved,
        "dry_run": dry_run,
        "allow_real": bool(context.get("allow_real")),
        "display": context.get("display"),
        "xauthority": context.get("xauthority"),
    }
    forward_context = {k: v for k, v in forward_context.items() if v is not None}

    if dry_run or context.get("dry_run"):
        return {
            "ok": True,
            "mode": "dry_run",
            "uri": uri,
            "payload": inner_payload,
            "context": forward_context,
            "would_forward_to": base_url,
        }

    result = _forward_uri(uri, inner_payload, forward_context, base_url)
    return {"ok": bool(result.get("ok")), "uri": uri, "forwarded_to": base_url, "result": result}
