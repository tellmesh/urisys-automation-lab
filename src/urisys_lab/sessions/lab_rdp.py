from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .util import copy_container_file, file_md5, http_json, save_json


def parse_lab_flow(path: Path) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    defaults = dict(data.get("defaults") or {})
    steps: list[tuple[str, dict[str, Any]]] = []
    for step in data.get("do") or []:
        if isinstance(step, str):
            steps.append((step, {}))
        elif isinstance(step, dict):
            if "uri" in step:
                steps.append((str(step["uri"]), dict(step.get("payload") or {})))
            else:
                uri, payload = next(iter(step.items()))
                steps.append((str(uri), dict(payload or {})))
    return defaults, steps


def flow_step_context(
    defaults: dict[str, Any],
    uri: str,
    *,
    display: str,
    xauth: str,
    real_mode: bool = False,
) -> dict[str, Any]:
    scheme = uri.split("://", 1)[0] if "://" in uri else ""
    ctx: dict[str, Any] = {"approved": True, "display": display, "xauthority": xauth}
    if real_mode:
        ctx["allow_real"] = scheme not in {"webrtc", "stt"}
        ctx["dry_run"] = scheme in {"webrtc", "stt"}
        if scheme in {"kvm", "rdp", "him", "ocr", "llm", "shell", "chat", "browser", "env", "stt", "webrtc"}:
            ctx["allow_real"] = True
            ctx["dry_run"] = False
        return ctx
    if scheme in {"kvm", "rdp", "him", "ocr", "llm"}:
        ctx["allow_real"] = True
        ctx["dry_run"] = False
    elif scheme in {"stt", "chat", "webrtc"}:
        ctx["dry_run"] = bool(defaults.get("dry_run", True))
        ctx["allow_real"] = False
    else:
        ctx["dry_run"] = bool(defaults.get("dry_run", True))
    return ctx


def step_pause(uri: str, *, real_mode: bool) -> None:
    if not real_mode:
        return
    scheme = uri.split("://", 1)[0] if "://" in uri else ""
    if scheme in {"him", "kvm", "shell", "chat", "browser"}:
        time.sleep(3.0)
    elif scheme in {"rdp"}:
        time.sleep(1.0)
    elif scheme in {"stt", "webrtc"}:
        time.sleep(2.0)


def summarize_uri_response(res: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": bool(res.get("ok")), "error": res.get("error")}
    result = res.get("result") or {}
    if not isinstance(result, dict):
        return out
    if result.get("mode") == "dry_run":
        out["mode"] = "dry_run"
    inner = result.get("result") or {}
    if isinstance(inner, dict):
        if "clicked" in inner:
            out["clicked"] = inner.get("clicked")
        if inner.get("result") and isinstance(inner["result"], dict):
            out["clicked"] = inner["result"].get("clicked", out.get("clicked"))
    for key in ("driver", "exit_code", "command", "hotkey", "engine"):
        if key in result:
            out[key] = result[key]
    return out


def parse_docker_log_errors(session_dir: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {"http_502": 0, "http_400": 0, "lines": []}
    noise = (
        "dbind-WARNING",
        "AT-SPI",
        "pm-is-supported",
        "Binding 'XF86",
        "Thumbnailer failed",
        "GLib-GObject-CRITICAL",
    )
    for name in ("docker-logs-lab.txt", "docker-logs-urirdp.txt", "docker-logs.txt"):
        path = session_dir / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        summary["http_502"] += text.count("502")
        summary["http_400"] += text.count("400")
        for line in text.splitlines():
            if not any(x in line for x in ('" 502 ', '" 400 ', "failed", "Error", "error")):
                continue
            if "health" in line.lower() and "200" in line:
                continue
            if any(n in line for n in noise):
                continue
            summary["lines"].append(f"{name}: {line.strip()[:200]}")
    summary["lines"] = summary["lines"][-40:]
    return summary


def prepare_ok_target(rdp_port: int, display: str, xauth: str) -> None:
    ctx = {"approved": True, "allow_real": True, "display": display, "xauthority": xauth}
    http_json(
        "POST",
        f"http://127.0.0.1:{rdp_port}/uri/call",
        {"uri": "rdp://local/session/command/prepare-target", "payload": {"text": "OK"}, "context": ctx},
    )
    time.sleep(2.0)


def capture_rdp_screenshot(
    session_dir: Path,
    *,
    rdp_port: int,
    display: str,
    xauth: str,
    container: str,
    filename: str,
) -> tuple[bool, str | None]:
    ctx = {"approved": True, "allow_real": True, "display": display, "xauthority": xauth}
    try:
        shot = http_json(
            "POST",
            f"http://127.0.0.1:{rdp_port}/uri/call",
            {"uri": "kvm://local/monitor/primary/query/screenshot", "payload": {}, "context": ctx},
        )
        rel = f"screenshots/{filename}"
        dest = session_dir / rel
        if copy_container_file(container, "/opt/urirdp/data/screenshots/latest.png", dest):
            return bool(shot.get("ok") and (shot.get("result") or {}).get("captured")), rel
        return False, None
    except Exception:
        return False, None


def capture_rdp_screenshot_wait(
    session_dir: Path,
    *,
    rdp_port: int,
    display: str,
    xauth: str,
    container: str,
    filename: str,
    avoid_md5s: set[str] | None = None,
    timeout_s: float = 12.0,
) -> tuple[bool, str | None]:
    avoid = {digest for digest in (avoid_md5s or set()) if digest}
    deadline = time.time() + timeout_s
    last: tuple[bool, str | None] = (False, None)
    while time.time() < deadline:
        captured, rel = capture_rdp_screenshot(
            session_dir,
            rdp_port=rdp_port,
            display=display,
            xauth=xauth,
            container=container,
            filename=filename,
        )
        last = (captured, rel)
        if rel:
            md5 = file_md5(session_dir / rel)
            if not avoid or (md5 and md5 not in avoid):
                return captured, rel
        time.sleep(0.6)
    return last
