"""Shared, side-effect-light primitives for test-session runners.

Both session runners (``run_test_sessions.py`` and ``lenovo_remote_session.py``)
need the same handful of pure helpers: timestamps, JSON dumping, the
pass/fail predicate for a recorded step, and base64-image extraction from URI
responses. They were duplicated; this is the single home so the two runners can
converge on one implementation.
"""

from __future__ import annotations

import base64
import json
import os
import platform
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PACK_TO_WHEEL: dict[str, str] = {
    "kv": "urikv",
    "browser": "uribrowser",
    "office": "urioffice",
    "mail": "urimail",
    "uriimg2nl": "uriimg2nl",
    "urivql": "urivql",
    "urisys_node": "urisys_node",
}


def default_examples_root(*, urisys_root: Path | None = None) -> Path:
    """Root of the urisys-examples repo (flow YAML suites)."""
    env = os.environ.get("URISYS_EXAMPLES_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    base = urisys_root or Path(__file__).resolve().parents[2]
    return (base.parent / "urisys-examples").resolve()


def resolve_flow_ref(ref: str | Path, *, suite_dir: Path, examples_root: Path) -> Path:
    """Resolve a flow path from manifest, CLI, or ``requires.upgrade``."""
    p = Path(ref)
    if p.is_absolute():
        return p
    if p.exists():
        return p.resolve()
    for candidate in (suite_dir / p, examples_root / p, suite_dir.parent / p):
        if candidate.is_file():
            return candidate.resolve()
    return (suite_dir / p).resolve()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def host_id() -> str:
    return f"{socket.gethostname()} ({platform.system()} {platform.machine()})"


def run_id(prefix: str = "", *, utc: bool = False) -> str:
    """Timestamped session id, e.g. '20260617-141828' or 'lenovo-remote-…' (utc)."""
    now = datetime.now(timezone.utc) if utc else datetime.now()
    return f"{prefix}{now.strftime('%Y%m%d-%H%M%S')}"


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _step_ok_http_get(result: dict[str, Any]) -> bool:
    return bool(result.get("response", {}).get("ok"))


def _step_ok_host_restart_and_wait(result: dict[str, Any]) -> bool:
    return bool(result.get("response", {}).get("ok")) and not result.get("error")


def _step_ok_host_schedule_restart(result: dict[str, Any]) -> bool:
    resp = result.get("response") or {}
    if resp.get("ok") is True:
        return True
    if resp.get("note") == "connection closed during takeover":
        return True
    return not result.get("error")


def _step_ok_default(result: dict[str, Any]) -> bool:
    resp = result.get("response")
    if isinstance(resp, dict):
        if resp.get("ok") is False:
            return False
        inner = resp.get("result")
        if isinstance(inner, dict) and inner.get("ok") is False:
            return False
        if isinstance(inner, dict) and inner.get("loaded") is False:
            return False
    return True


_KIND_OK: dict[str, Any] = {
    "http_get": _step_ok_http_get,
    "host_wait_health": _step_ok_http_get,
    "host_restart_and_wait": _step_ok_host_restart_and_wait,
    "host_schedule_restart": _step_ok_host_schedule_restart,
}


def step_ok(result: dict[str, Any]) -> bool:
    """Whether a recorded step succeeded: no transport error and no inner ok=False."""
    if result.get("error"):
        return False
    checker = _KIND_OK.get(result.get("kind"))
    if checker is not None:
        return checker(result)
    return _step_ok_default(result)


def image_ext(mime: str) -> str:
    mime = (mime or "image/png").lower()
    if "jpeg" in mime or "jpg" in mime:
        return "jpg"
    if "webp" in mime:
        return "webp"
    return "png"


def write_base64_image(b64: str, dest: Path) -> int:
    raw = base64.b64decode(b64)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    return len(raw)


def extract_images_from_dict(
    obj: dict[str, Any],
    *,
    session_dir: Path,
    filename: str,
    strip_base64: bool,
) -> list[str]:
    """Extract a base64 image (and nested shots[]) from a dict into screenshots/."""
    saved: list[str] = []
    b64 = obj.get("base64")
    if isinstance(b64, str) and len(b64) > 100:
        rel = f"screenshots/{filename}.{image_ext(str(obj.get('mime') or ''))}"
        size = write_base64_image(b64, session_dir / rel)
        saved.append(rel)
        if strip_base64:
            obj.pop("base64", None)
            obj["screenshot_file"] = rel
            obj["screenshot_bytes"] = size

    shots = obj.get("shots")
    if isinstance(shots, list):
        for i, shot in enumerate(shots):
            if isinstance(shot, dict):
                saved.extend(
                    extract_images_from_dict(
                        shot,
                        session_dir=session_dir,
                        filename=f"{filename}_shot{i}",
                        strip_base64=strip_base64,
                    )
                )
    return saved


def extract_step_screenshots(
    step: dict[str, Any],
    *,
    session_dir: Path,
    flow_id: str,
    strip_base64: bool = True,
) -> list[str]:
    """Write embedded base64 from a URI-response step into session_dir/screenshots/."""
    resp = step.get("response")
    if not isinstance(resp, dict):
        return []
    result = resp.get("result")
    if not isinstance(result, dict):
        return []
    step_id = str(step.get("id") or "step")
    saved = extract_images_from_dict(
        result,
        session_dir=session_dir,
        filename=f"{flow_id}__{step_id}",
        strip_base64=strip_base64,
    )
    if saved:
        step["screenshots"] = saved
    return saved


def backfill_session_images(session_dir: Path, *, strip_base64: bool = True) -> list[str]:
    """Extract images from all response JSON files (also for past sessions)."""
    responses = session_dir / "responses"
    if not responses.is_dir():
        return []
    all_saved: list[str] = []
    for path in sorted(responses.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        flow_id, _, step_id = path.stem.partition("__")
        if not step_id:
            continue
        data["id"] = step_id
        saved = extract_step_screenshots(
            data, session_dir=session_dir, flow_id=flow_id, strip_base64=strip_base64
        )
        if saved:
            save_json(path, data)
            all_saved.extend(saved)
    return all_saved


def _wheel_version_key(path: Path, prefix: str) -> tuple:
    """Parse ``prefix-1.2.3-py3-none-any.whl`` for semver ordering."""
    name = path.name
    if not name.startswith(f"{prefix}-") or not name.endswith(".whl"):
        return (0,)
    ver_part = name[len(prefix) + 1 : -4].split("-py", 1)[0]
    key: list[Any] = []
    for piece in ver_part.split("."):
        try:
            key.append(int(piece))
        except ValueError:
            key.append(piece)
    return tuple(key)


def find_wheel_file(deploy_dir: Path, prefix: str) -> Path | None:
    candidates = list(deploy_dir.glob(f"{prefix}-*.whl"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: _wheel_version_key(p, prefix))


def wheel_url(wheel_server: str, wheel_path: Path) -> str:
    return f"{wheel_server.rstrip('/')}/{wheel_path.name}"


def _resolve_wheel_name(step: dict[str, Any], payload: dict[str, Any]) -> str | None:
    wheel_name = step.pop("wheel", None)
    if wheel_name:
        return str(wheel_name)
    pack = payload.get("pack")
    if (
        isinstance(pack, str)
        and pack in PACK_TO_WHEEL
        and not payload.get("specs")
        and payload.get("install")
    ):
        return PACK_TO_WHEEL[pack]
    return None


def _apply_wheel_refspec(
    payload: dict[str, Any], wheel_name: str, *, wheel_server: str, deploy_dir: Path
) -> dict[str, Any]:
    whl = find_wheel_file(deploy_dir, wheel_name)
    if whl:
        specs = list(payload.get("specs") or [])
        if not specs:
            specs = ["uricore>=0.1.0", wheel_url(wheel_server, whl)]
        payload["specs"] = specs
    return payload


def _resolve_wheel_args(
    payload: dict[str, Any], *, wheel_server: str, deploy_dir: Path
) -> dict[str, Any]:
    if not isinstance(payload.get("args"), list):
        return payload
    new_args: list[Any] = []
    for arg in payload["args"]:
        if isinstance(arg, str) and arg.startswith("{wheel:") and arg.endswith("}"):
            name = arg[7:-1]
            whl = find_wheel_file(deploy_dir, name)
            new_args.append(wheel_url(wheel_server, whl) if whl else arg)
        else:
            new_args.append(arg)
    payload = dict(payload)
    payload["args"] = new_args
    return payload


def expand_step_wheels(
    step: dict[str, Any],
    *,
    wheel_server: str,
    deploy_dir: Path,
) -> dict[str, Any]:
    """Resolve ``wheel:`` / ``{wheel:pkg}`` placeholders to concrete wheel URLs."""
    step = dict(step)
    payload = dict(step.get("payload") or {})

    wheel_name = _resolve_wheel_name(step, payload)
    if wheel_name:
        payload = _apply_wheel_refspec(payload, wheel_name, wheel_server=wheel_server, deploy_dir=deploy_dir)
        step["payload"] = payload

    payload = _resolve_wheel_args(step.get("payload") or payload, wheel_server=wheel_server, deploy_dir=deploy_dir)
    step["payload"] = payload
    return step
