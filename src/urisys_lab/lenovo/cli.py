#!/usr/bin/env python3
"""Run remote URI flow suites from urisys-examples, save responses, write session report.

Flows live in ``../urisys-examples/`` (override with ``URISYS_EXAMPLES_ROOT`` or ``--examples-root``).

  python3 scripts/lenovo_remote_session.py
  python3 scripts/lenovo_remote_session.py --wait 120 --build-wheels
  python3 scripts/lenovo_remote_session.py --flows lenovo-remote/08-kvm-linkedin.uri.flow.yaml

Single step via Python CLI (no bash scripts):

  python3 -m urisysnode.remote call "kv://lenovo/runtime/query/discover"
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from urisys_lab.core import (
    backfill_session_images,
    default_examples_root,
    expand_step_wheels,
    extract_step_screenshots,
    now_iso,
    resolve_flow_ref,
    save_json,
    step_ok,
)
from urisys_lab.paths import NODE_ROOT, URISYS_ROOT

if str(NODE_ROOT) not in sys.path:
    sys.path.insert(0, str(NODE_ROOT))

from urisysnode.remote import (
    call_uri,
    default_endpoint,
    default_route_map,
    health as remote_health,
    schedule_restart,
    wait_health,
)

ROOT = URISYS_ROOT
EXAMPLES_ROOT = default_examples_root(urisys_root=ROOT)
DEFAULT_MANIFEST = EXAMPLES_ROOT / "lenovo-remote" / "session.manifest.yaml"

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

# Wheel server on the dev host (192.168.188.212) serving locally-built wheels to
# the lenovo slave; overridable per-session via manifest `wheel_server:`.
DEFAULT_WHEEL_SERVER = "http://192.168.188.212:8765"


def load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else {}
    # minimal fallback: only for manifest listing — flows need pyyaml
    raise RuntimeError("PyYAML required: pip install pyyaml")


def http_get(endpoint: str, path: str, *, timeout: float = 30.0) -> dict[str, Any]:
    url = endpoint.rstrip("/") + path
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                data = {"raw": body}
            return {"ok": True, "url": url, "status": resp.status, "body": data}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "url": url, "status": exc.code, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "url": url, "error": str(exc)}


def _run_http_get_step(step: dict[str, Any], out: dict[str, Any], endpoint: str) -> None:
    out["kind"] = "http_get"
    out["response"] = http_get(endpoint, str(step.get("path") or "/health"))


def _run_host_sleep_step(step: dict[str, Any], out: dict[str, Any]) -> None:
    seconds = float(step.get("seconds") or step.get("sleep") or 5)
    out["kind"] = "host_sleep"
    out["seconds"] = seconds
    time.sleep(seconds)
    out["response"] = {"ok": True, "slept": seconds}


def _schedule_restart_safely(endpoint: str, route_map: str) -> dict[str, Any] | str:
    """Return either restart response dict or error string."""
    try:
        return schedule_restart(endpoint=endpoint, route_map=route_map)
    except Exception as exc:
        msg = str(exc)
        if "Remote end closed connection" in msg or "Connection reset" in msg:
            return msg
        raise


def _poll_health_after_restart(
    endpoint: str,
    *,
    timeout: float,
    settle_s: float,
    baseline_id: str | None,
    expect: dict[str, Any],
) -> dict[str, Any]:
    time.sleep(settle_s)
    deadline = time.time() + timeout
    last: dict[str, Any] = {"ok": False, "error": "unreachable"}
    while time.time() < deadline:
        try:
            last = remote_health(endpoint=endpoint)
        except Exception as exc:
            last = {"ok": False, "error": str(exc)}
            time.sleep(2.0)
            continue
        if not last.get("ok"):
            time.sleep(2.0)
            continue
        if expect and not all(last.get(k) == v for k, v in expect.items()):
            time.sleep(2.0)
            continue
        new_id = last.get("instance_id")
        if baseline_id and new_id == baseline_id:
            time.sleep(2.0)
            continue
        return last
    return last


def _run_host_restart_and_wait_step(
    step: dict[str, Any],
    out: dict[str, Any],
    *,
    endpoint: str,
    route_map: str,
) -> dict[str, Any] | None:
    """Return out early on fatal error, otherwise set out fields in place."""
    timeout = float(step.get("timeout") or step.get("seconds") or 90)
    expect = step.get("expect") if isinstance(step.get("expect"), dict) else {}
    settle_s = float(step.get("settle_s") or 3)
    out["kind"] = "host_restart_and_wait"
    out["timeout"] = timeout
    if expect:
        out["expect"] = expect
    baseline = remote_health(endpoint=endpoint)
    baseline_id = baseline.get("instance_id")
    out["baseline_instance_id"] = baseline_id

    restart_result = _schedule_restart_safely(endpoint, route_map)
    if isinstance(restart_result, str):
        out["restart"] = {"ok": True, "note": "connection closed during takeover", "error": restart_result}
    else:
        out["restart"] = restart_result

    last = _poll_health_after_restart(
        endpoint, timeout=timeout, settle_s=settle_s, baseline_id=baseline_id, expect=expect
    )
    if last.get("instance_id") != baseline_id and not (
        expect and not all(last.get(k) == v for k, v in expect.items())
    ):
        out["response"] = last
        return None
    out["error"] = (
        f"restart wait failed after {timeout}s expect={expect!r} "
        f"baseline={baseline_id!r} last={last!r}"
    )
    out["response"] = last
    return None


def _run_host_schedule_restart_step(
    step: dict[str, Any], out: dict[str, Any], *, endpoint: str, route_map: str
) -> None:
    out["kind"] = "host_schedule_restart"
    try:
        out["response"] = schedule_restart(endpoint=endpoint, route_map=route_map)
    except Exception as exc:
        msg = str(exc)
        if "Remote end closed connection" in msg or "Connection reset" in msg:
            out["response"] = {"ok": True, "note": "connection closed during takeover", "error": msg}
        else:
            out["error"] = msg
            out["response"] = {"ok": False, "error": msg}


def _run_host_wait_health_step(step: dict[str, Any], out: dict[str, Any], *, endpoint: str) -> None:
    timeout = float(step.get("timeout") or step.get("seconds") or 60)
    expect = step.get("expect") if isinstance(step.get("expect"), dict) else {}
    out["kind"] = "host_wait_health"
    out["timeout"] = timeout
    if expect:
        out["expect"] = expect
    deadline = time.time() + timeout
    last: dict[str, Any] = {"ok": False, "error": "unreachable"}
    try:
        while time.time() < deadline:
            try:
                last = remote_health(endpoint=endpoint)
            except Exception as exc:
                last = {"ok": False, "error": str(exc)}
                time.sleep(2.0)
                continue
            if last.get("ok") and all(last.get(k) == v for k, v in expect.items()):
                out["response"] = last
                break
            time.sleep(2.0)
        else:
            out["error"] = f"health expect not met after {timeout}s: {expect!r} last={last!r}"
            out["response"] = last
    except TimeoutError as exc:
        out["error"] = str(exc)
        out["response"] = {"ok": False, "error": str(exc)}


def _run_uri_call_step(
    step: dict[str, Any],
    out: dict[str, Any],
    *,
    route_map: str,
    defaults: dict[str, Any],
) -> None:
    uri = str(step.get("uri") or "")
    if not uri:
        raise ValueError("step requires uri or kind:http_get")
    payload = dict(step.get("payload") or {})
    ctx = {
        "approved": bool(defaults.get("approved", True)),
        "dry_run": bool(defaults.get("dry_run", False)),
        "allow_real": bool(defaults.get("allow_real", True)),
    }
    for key in ("approved", "dry_run", "allow_real"):
        if key in step:
            ctx[key] = bool(step[key])
    out["kind"] = "uri_call"
    out["uri"] = uri
    out["payload"] = payload
    out["context"] = ctx
    out["response"] = call_uri(
        uri,
        payload=payload,
        approved=ctx["approved"],
        dry_run=ctx["dry_run"],
        allow_real=ctx["allow_real"],
        route_map=route_map,
    )


def run_step(
    step: dict[str, Any],
    *,
    endpoint: str,
    route_map: str,
    defaults: dict[str, Any],
) -> dict[str, Any]:
    step_id = str(step.get("id") or "step")
    kind = step.get("kind")
    started = now_iso()
    out: dict[str, Any] = {"id": step_id, "started_at": started, "note": step.get("note")}

    try:
        if kind == "http_get":
            _run_http_get_step(step, out, endpoint)
        elif kind == "host_sleep":
            _run_host_sleep_step(step, out)
        elif kind == "host_restart_and_wait":
            early = _run_host_restart_and_wait_step(step, out, endpoint=endpoint, route_map=route_map)
            if early is not None:
                return early
        elif kind == "host_schedule_restart":
            _run_host_schedule_restart_step(step, out, endpoint=endpoint, route_map=route_map)
        elif kind == "host_wait_health":
            _run_host_wait_health_step(step, out, endpoint=endpoint)
        else:
            _run_uri_call_step(step, out, route_map=route_map, defaults=defaults)
    except Exception as exc:
        out["error"] = str(exc)
        out["response"] = {"ok": False, "error": str(exc)}

    out["finished_at"] = now_iso()
    out["ok"] = step_ok(out)
    return out


def run_flow(
    flow_path: Path,
    *,
    endpoint: str,
    route_map: str,
    session_dir: Path,
    wheel_server: str,
    wheel_deploy_dir: Path,
    examples_root: Path,
) -> dict[str, Any]:
    data = load_yaml(flow_path)
    flow = data.get("flow") or {}
    flow_id = str(flow.get("id") or flow_path.stem)
    defaults = dict(data.get("defaults") or {})
    steps_raw = data.get("do") or []

    record: dict[str, Any] = {
        "flow_id": flow_id,
        "flow_path": str(flow_path.relative_to(examples_root) if flow_path.is_relative_to(examples_root) else flow_path),
        "description": flow.get("description"),
        "started_at": now_iso(),
        "steps": [],
    }

    for raw in steps_raw:
        if isinstance(raw, str):
            step = {"id": raw.split("://", 1)[0], "uri": raw}
        elif isinstance(raw, dict) and len(raw) == 1 and not raw.get("id"):
            uri, payload = next(iter(raw.items()))
            step = {"id": uri.replace("://", "-").replace("/", "-")[:40], "uri": uri}
            if isinstance(payload, dict):
                step["payload"] = payload
        else:
            step = dict(raw)
        step = expand_step_wheels(step, wheel_server=wheel_server, deploy_dir=wheel_deploy_dir)
        result = run_step(step, endpoint=endpoint, route_map=route_map, defaults=defaults)
        extract_step_screenshots(result, session_dir=session_dir, flow_id=flow_id)
        record["steps"].append(result)
        save_json(session_dir / "responses" / f"{flow_id}__{result['id']}.json", result)

    record["finished_at"] = now_iso()
    record["ok"] = all(s.get("ok") for s in record["steps"]) if record["steps"] else False
    save_json(session_dir / "flows" / f"{flow_id}.json", record)
    return record


def append_log(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")


def build_wheels(deploy_dir: Path) -> None:
    deploy_dir.mkdir(parents=True, exist_ok=True)
    tellmesh = ROOT.parent
    for pkg in ("urikv", "uribrowser", "urioffice", "urimail", "uriimg2nl", "urivql", "urisys-node"):
        pkg_dir = tellmesh / pkg
        if pkg_dir.is_dir():
            subprocess.run(
                [sys.executable, "-m", "pip", "wheel", "-w", str(deploy_dir), str(pkg_dir), "-q"],
                check=False,
            )
    profile = tellmesh / "urisys-node" / "config" / "node-profile.lenovo.json"
    if profile.is_file():
        shutil.copy2(profile, deploy_dir / "node-profile.lenovo.json")


def start_wheel_server(deploy_dir: Path, host: str, port: int) -> subprocess.Popen[Any] | None:
    try:
        urllib.request.urlopen(f"http://{host}:{port}/", timeout=1)
        return None
    except Exception:
        pass
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", host, "--directory", str(deploy_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)
    return proc


def _needs_node_upgrade(flow_paths: list[Path]) -> bool:
    names = {p.name for p in flow_paths}
    return bool(
        names
        & {
            "02-install-packs.uri.flow.yaml",
            "07-playwright-linkedin.uri.flow.yaml",
        }
        or any("install-packs" in p.name for p in flow_paths)
    )


def _run_upgrade_flow(
    upgrade_flow: Path,
    label: str,
    *,
    log_path: Path,
    flow_records: list[dict[str, Any]],
    _run_one: Any,
) -> dict[str, Any]:
    """Execute an upgrade flow, log it, append to records, return the record."""
    append_log(log_path, f"flow {upgrade_flow.name} start ({label})")
    rec = _run_one(upgrade_flow)
    flow_records.append(rec)
    append_log(log_path, f"flow {upgrade_flow.name} ok={rec.get('ok')}")
    return rec


def _md_header(meta: dict[str, Any], session_dir: Path) -> list[str]:
    return [
        "# Lenovo remote session",
        "",
        f"- **Session ID:** `{meta['session_id']}`",
        f"- **Started:** {meta['started_at']}",
        f"- **Host (dev):** {meta['host']}",
        f"- **Target:** {meta['endpoint']}",
        f"- **Node reachable at start:** {meta.get('node_reachable')}",
        "",
        "## Replay",
        "",
        "```bash",
        f"cd {ROOT}",
        "python3 scripts/lenovo_remote_session.py --session-dir " + str(session_dir.relative_to(ROOT)),
        "```",
        "",
        "Or single URI:",
        "",
        "```bash",
        "cd " + str(NODE_ROOT),
        'python3 -m urisysnode.remote call "kv://lenovo/runtime/query/discover"',
        "```",
        "",
    ]


def _md_flow_results(flow_records: list[dict[str, Any]]) -> list[str]:
    lines = [
        "## Flow results",
        "",
        "| Flow | OK | Steps pass | Notes |",
        "|------|-----|------------|-------|",
    ]
    for fr in flow_records:
        passed = sum(1 for s in fr.get("steps", []) if s.get("ok"))
        total = len(fr.get("steps", []))
        note = fr.get("description") or ""
        lines.append(
            f"| `{fr['flow_id']}` | {'✅' if fr.get('ok') else '❌'} | {passed}/{total} | {note[:60]} |"
        )
    return lines


def _md_step_detail(flow_records: list[dict[str, Any]]) -> list[str]:
    lines = ["", "## Step detail", ""]
    for fr in flow_records:
        lines.append(f"### {fr['flow_id']}")
        lines.append("")
        for step in fr.get("steps", []):
            icon = "✅" if step.get("ok") else "❌"
            uri = step.get("uri") or step.get("response", {}).get("url") or step.get("kind")
            err = step.get("error") or (step.get("response") or {}).get("error")
            lines.append(f"- {icon} **{step['id']}** — `{uri}`")
            if err:
                lines.append(f"  - error: `{err}`")
            if step.get("note"):
                lines.append(f"  - note: {step['note']}")
            for shot in step.get("screenshots") or []:
                lines.append(f"  - screenshot: `{shot}`")
        lines.append("")
    return lines


def _md_lessons(meta: dict[str, Any], flow_records: list[dict[str, Any]]) -> list[str]:
    lines = ["## Lessons", ""]
    if not meta.get("node_reachable"):
        lines.append("- Node was **down** at session start — start on lenovo: `source ~/venv/bin/activate && urisys node serve --host 0.0.0.0 --port 8790`")
    failed = [s for fr in flow_records for s in fr.get("steps", []) if not s.get("ok")]
    if failed:
        lines.append(f"- **{len(failed)}** step(s) failed — see `responses/*.json`")
    else:
        lines.append("- All steps passed.")
    lines.append("")
    return lines


def write_session_md(session_dir: Path, meta: dict[str, Any], flow_records: list[dict[str, Any]]) -> None:
    lines = (
        _md_header(meta, session_dir)
        + _md_flow_results(flow_records)
        + _md_step_detail(flow_records)
        + _md_lessons(meta, flow_records)
    )
    (session_dir / "SESSION.md").write_text("\n".join(lines), encoding="utf-8")
    lines.append("## Artifacts")
    lines.append("")
    lines.append(f"- Flow copies: `{session_dir.relative_to(ROOT)}/flows/`")
    lines.append(f"- Responses: `{session_dir.relative_to(ROOT)}/responses/`")
    lines.append(f"- Screenshots: `{session_dir.relative_to(ROOT)}/screenshots/` (extracted from base64)")
    lines.append(f"- Manifest: `{meta.get('manifest_path', 'session.manifest.yaml')}`")
    lines.append("")

    (session_dir / "SESSION.md").write_text("\n".join(lines), encoding="utf-8")


def resolve_flow_paths(
    manifest_path: Path,
    explicit: list[str] | None,
    *,
    examples_root: Path,
) -> list[Path]:
    suite_dir = manifest_path.parent.resolve()
    if explicit:
        return [resolve_flow_ref(p, suite_dir=suite_dir, examples_root=examples_root) for p in explicit]
    data = load_yaml(manifest_path)
    flows = data.get("flows") or []
    return [resolve_flow_ref(f, suite_dir=suite_dir, examples_root=examples_root) for f in flows]


def resolve_route_map(manifest_path: Path, cli_route_map: str | None) -> str:
    if cli_route_map and cli_route_map != default_route_map():
        return cli_route_map
    data = load_yaml(manifest_path)
    session = data.get("session") if isinstance(data.get("session"), dict) else {}
    rel = session.get("route_map")
    if isinstance(rel, str) and rel.strip():
        candidate = (manifest_path.parent / rel).resolve()
        if candidate.is_file():
            return str(candidate)
    return cli_route_map or default_route_map()


def load_manifest_session(manifest_path: Path) -> dict[str, Any]:
    data = load_yaml(manifest_path)
    return data.get("session") if isinstance(data.get("session"), dict) else {}


def _check_and_restore_health(
    fp: Path,
    *,
    endpoint: str,
    node_reachable: bool,
    meta: dict[str, Any],
    log_path: Path,
    session_dir: Path,
) -> bool:
    if fp.name == "01-health-probe.uri.flow.yaml":
        return node_reachable
    try:
        health_data = remote_health(endpoint=endpoint)
        node_reachable = bool(health_data.get("ok"))
        if node_reachable:
            meta["node_reachable"] = True
            save_json(session_dir / "responses" / "_00_preflight_health.json", health_data)
    except Exception as exc:
        node_reachable = False
        append_log(log_path, f"health re-check failed: {exc}")
    return node_reachable


def _skip_node_down(
    fp: Path,
    *,
    node_reachable: bool,
    examples_root: Path,
    session_dir: Path,
    log_path: Path,
    flow_records: list[dict[str, Any]],
) -> bool:
    if node_reachable or fp.name == "01-health-probe.uri.flow.yaml":
        return False
    rec = {
        "flow_id": load_yaml(fp).get("flow", {}).get("id", fp.stem),
        "flow_path": str(
            fp.relative_to(examples_root) if fp.is_relative_to(examples_root) else fp
        ),
        "ok": False,
        "skipped": True,
        "reason": "node unreachable (see 01-health-probe)",
        "steps": [],
    }
    flow_records.append(rec)
    save_json(session_dir / "flows" / f"{rec['flow_id']}.json", rec)
    append_log(log_path, f"flow {fp.name} skipped (node down)")
    return True


def _maybe_run_node_upgrade(
    fp: Path,
    flow_paths: list[Path],
    *,
    node_upgrade_ran: bool,
    meta: dict[str, Any],
    log_path: Path,
    flow_records: list[dict[str, Any]],
    _run_one: Any,
) -> bool:
    if (
        node_upgrade_ran
        or not UPGRADE_NODE_FLOW.exists()
        or not _needs_node_upgrade(flow_paths)
        or fp.name == "01-health-probe.uri.flow.yaml"
    ):
        return node_upgrade_ran
    node_rec = _run_upgrade_flow(
        UPGRADE_NODE_FLOW, "urisys-node wheel",
        log_path=log_path, flow_records=flow_records, _run_one=_run_one,
    )
    node_upgrade_ran = True
    if not node_rec.get("ok"):
        append_log(log_path, f"flow {fp.name} skipped (node upgrade failed)")
        return False
    meta["node_reachable"] = True
    return True


def _maybe_run_kvm_upgrade(
    fp: Path,
    *,
    kvm_upgrade_ran: bool,
    log_path: Path,
    flow_records: list[dict[str, Any]],
    _run_one: Any,
) -> bool:
    if (
        fp.name != "08-kvm-linkedin.uri.flow.yaml"
        or not UPGRADE_KVM_FLOW.exists()
        or kvm_upgrade_ran
    ):
        return True
    kvm_rec = _run_upgrade_flow(
        UPGRADE_KVM_FLOW, "pre-08 kvm upgrade",
        log_path=log_path, flow_records=flow_records, _run_one=_run_one,
    )
    if not kvm_rec.get("ok"):
        append_log(log_path, f"flow {fp.name} skipped (kvm upgrade failed)")
        return False
    return True


def _maybe_run_playwright_upgrade(
    fp: Path,
    *,
    upgrade_ran: bool,
    meta: dict[str, Any],
    log_path: Path,
    flow_records: list[dict[str, Any]],
    _run_one: Any,
) -> bool:
    if (
        fp.name != "07-playwright-linkedin.uri.flow.yaml"
        or not UPGRADE_PLAYWRIGHT_FLOW.exists()
        or upgrade_ran
    ):
        return True
    up_rec = _run_upgrade_flow(
        UPGRADE_PLAYWRIGHT_FLOW, "pre-07 upgrade",
        log_path=log_path, flow_records=flow_records, _run_one=_run_one,
    )
    if not up_rec.get("ok"):
        append_log(log_path, f"flow {fp.name} skipped (upgrade failed)")
        return False
    meta["node_reachable"] = True
    return True


def _run_flows(
    flow_paths: list[Path],
    *,
    _run_one: Any,
    endpoint: str,
    node_reachable: bool,
    meta: dict[str, Any],
    log_path: Path,
    session_dir: Path,
    examples_root: Path,
) -> tuple[list[dict[str, Any]], bool]:
    """Execute each flow in order, running upgrade flows on demand."""
    flow_records: list[dict[str, Any]] = []
    upgrade_ran = False
    kvm_upgrade_ran = False
    node_upgrade_ran = False

    for fp in flow_paths:
        append_log(log_path, f"flow {fp.name} start")
        if not fp.exists():
            rec = {"flow_id": fp.stem, "ok": False, "error": "flow file missing", "steps": []}
            flow_records.append(rec)
            continue

        node_reachable = _check_and_restore_health(
            fp, endpoint=endpoint, node_reachable=node_reachable,
            meta=meta, log_path=log_path, session_dir=session_dir,
        )

        if _skip_node_down(fp, node_reachable=node_reachable, examples_root=examples_root,
                           session_dir=session_dir, log_path=log_path, flow_records=flow_records):
            continue

        nr = _maybe_run_node_upgrade(
            fp, flow_paths, node_upgrade_ran=node_upgrade_ran,
            meta=meta, log_path=log_path, flow_records=flow_records, _run_one=_run_one,
        )
        if nr is False:
            continue
        node_upgrade_ran = True

        if not _maybe_run_kvm_upgrade(
            fp, kvm_upgrade_ran=kvm_upgrade_ran,
            log_path=log_path, flow_records=flow_records, _run_one=_run_one,
        ):
            kvm_upgrade_ran = True
            continue
        kvm_upgrade_ran = True

        if not _maybe_run_playwright_upgrade(
            fp, upgrade_ran=upgrade_ran,
            meta=meta, log_path=log_path, flow_records=flow_records, _run_one=_run_one,
        ):
            upgrade_ran = True
            continue
        upgrade_ran = True

        rec = _run_one(fp)
        flow_records.append(rec)
        append_log(log_path, f"flow {fp.name} ok={rec.get('ok')}")

    return flow_records, node_reachable


UPGRADE_PLAYWRIGHT_FLOW = EXAMPLES_ROOT / "lenovo-remote/_upgrade-playwright.uri.flow.yaml"
UPGRADE_KVM_FLOW = EXAMPLES_ROOT / "lenovo-remote/_upgrade-kvm.uri.flow.yaml"
UPGRADE_NODE_FLOW = EXAMPLES_ROOT / "lenovo-remote/_upgrade-node.uri.flow.yaml"


def _run_extract_images(extract_images: str) -> int:
    session_dir = Path(extract_images)
    if not session_dir.is_dir():
        print(json.dumps({"ok": False, "error": f"not a directory: {session_dir}"}), file=sys.stderr)
        return 2
    saved = backfill_session_images(session_dir)
    print(json.dumps({"ok": True, "session_dir": str(session_dir), "screenshots": saved}, indent=2))
    return 0


def _ensure_pyyaml() -> bool:
    if yaml is None:
        print("ERROR: pip install pyyaml", file=sys.stderr)
        return False
    return True


def _init_session(run_id: str, session_dir_arg: str) -> tuple[Path, Path]:
    run_id = run_id or datetime.now(timezone.utc).strftime("lenovo-remote-%Y%m%d-%H%M%S")
    session_dir = Path(session_dir_arg) if session_dir_arg else ROOT / "output" / "test-sessions" / run_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "responses").mkdir(exist_ok=True)
    (session_dir / "flows").mkdir(exist_ok=True)
    return session_dir, session_dir / "session.log"


def _setup_wheels(
    args: argparse.Namespace,
    session_cfg: dict[str, Any],
) -> subprocess.Popen[Any] | None:
    wheel_server = str(session_cfg.get("wheel_server") or DEFAULT_WHEEL_SERVER)
    wheel_deploy_dir = Path(str(session_cfg.get("wheel_deploy_dir") or "/tmp/urisys-deploy"))
    wheel_proc = None
    if args.build_wheels:
        build_wheels(wheel_deploy_dir)
    if args.serve_wheels:
        parsed_ws = urllib.parse.urlparse(wheel_server)
        default_ws = urllib.parse.urlparse(DEFAULT_WHEEL_SERVER)
        host = parsed_ws.hostname or default_ws.hostname
        port = parsed_ws.port or default_ws.port
        wheel_proc = start_wheel_server(wheel_deploy_dir, host, port)
    return wheel_proc


def _check_initial_health(
    endpoint: str, *, wait: float, log_path: Path
) -> tuple[bool, dict[str, Any]]:
    node_reachable = False
    health_data: dict[str, Any] = {}
    append_log(log_path, f"[{now_iso()}] session start target={endpoint}")

    if wait > 0:
        append_log(log_path, f"waiting up to {wait}s for node")
        try:
            health_data = wait_health(endpoint=endpoint, timeout_s=wait)
            node_reachable = bool(health_data.get("ok"))
        except TimeoutError as exc:
            append_log(log_path, f"wait failed: {exc}")
    else:
        try:
            health_data = remote_health(endpoint=endpoint)
            node_reachable = bool(health_data.get("ok"))
        except Exception as exc:
            append_log(log_path, f"health failed: {exc}")
            health_data = {"ok": False, "error": str(exc)}
    return node_reachable, health_data


def _copy_flow_sources(
    flow_paths: list[Path], manifest_path: Path, session_dir: Path
) -> None:
    flows_copy = session_dir / "flow-sources"
    flows_copy.mkdir(exist_ok=True)
    for fp in flow_paths:
        if fp.exists():
            shutil.copy2(fp, flows_copy / fp.name)
    shutil.copy2(manifest_path, session_dir / "session.manifest.yaml")


def _build_meta(
    run_id: str,
    session_cfg: dict[str, Any],
    node_reachable: bool,
    args: argparse.Namespace,
    route_map: str,
    examples_root: Path,
    manifest_path: Path,
    flow_paths: list[Path],
) -> dict[str, Any]:
    return {
        "session_id": run_id,
        "session_name": session_cfg.get("id") or "lenovo-remote",
        "suite": "remote-node-flows",
        "started_at": now_iso(),
        "host": os.uname().nodename,
        "endpoint": args.endpoint,
        "route_map": route_map,
        "examples_root": str(examples_root),
        "manifest_path": str(manifest_path),
        "node_reachable": node_reachable,
        "flow_files": [
            str(p.relative_to(examples_root) if p.is_relative_to(examples_root) else p) for p in flow_paths
        ],
    }


def _collect_step_summaries(
    meta: dict[str, Any], flow_records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {
            "name": f"{rec.get('flow_id', 'flow')}__{s['id']}",
            "status": "pass" if s.get("ok") else "fail",
            "uri": s.get("uri"),
            "response_file": f"responses/{rec.get('flow_id', 'flow')}__{s['id']}.json",
            "screenshot": (s.get("screenshots") or [None])[0],
            "detail": "" if s.get("ok") else str(s.get("error") or "not ok")[:300],
        }
        for rec in flow_records
        for s in rec.get("steps") or []
    ]


def _session_result(node_reachable: bool, flow_records: list, wheel_proc, log_path: Path, session_dir: Path, meta: dict) -> int:
    if wheel_proc:
        wheel_proc.terminate()
    append_log(log_path, f"session done dir={session_dir}")
    print(json.dumps({"session_dir": str(session_dir), "node_reachable": node_reachable, "meta": meta}, indent=2))
    return 0 if node_reachable and all(r.get("ok") for r in flow_records if not r.get("skipped")) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lenovo remote session runner (flow-based, Python only).")
    parser.add_argument("--endpoint", default=os.environ.get("URISYS_LENOVO_ENDPOINT", default_endpoint()))
    parser.add_argument("--route-map", default=None, help="Route map YAML (default: manifest session.route_map)")
    parser.add_argument(
        "--examples-root",
        default=str(EXAMPLES_ROOT),
        help="Root of urisys-examples (or URISYS_EXAMPLES_ROOT)",
    )
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Session manifest YAML")
    parser.add_argument(
        "--flows",
        nargs="*",
        help="Flow files relative to examples root or suite dir (default: all from manifest)",
    )
    parser.add_argument("--wait", type=float, default=0, help="Wait up to N seconds for node /health")
    parser.add_argument("--build-wheels", action="store_true", help="Build pack wheels to /tmp/urisys-deploy")
    parser.add_argument("--serve-wheels", action="store_true", help="Start python -m http.server for wheels")
    parser.add_argument("--session-dir", default="", help="Reuse existing session dir (replay doc only)")
    parser.add_argument("--run-id", default="")
    parser.add_argument(
        "--extract-images",
        metavar="SESSION_DIR",
        help="Extract base64 images from existing session responses to screenshots/ (no flows run)",
    )
    args = parser.parse_args(argv)

    if args.extract_images:
        return _run_extract_images(args.extract_images)

    if not _ensure_pyyaml():
        return 2

    session_dir, log_path = _init_session(args.run_id, args.session_dir)

    manifest_path = Path(args.manifest).resolve()
    examples_root = Path(args.examples_root).expanduser().resolve()
    if not manifest_path.is_file():
        print(json.dumps({"ok": False, "error": f"manifest not found: {manifest_path}"}), file=sys.stderr)
        return 2

    route_map = resolve_route_map(manifest_path, args.route_map or os.environ.get("URISYS_ROUTE_MAP"))
    session_cfg = load_manifest_session(manifest_path)

    wheel_proc = _setup_wheels(args, session_cfg)

    node_reachable, health_data = _check_initial_health(args.endpoint, wait=args.wait, log_path=log_path)
    save_json(session_dir / "responses" / "_00_preflight_health.json", health_data)

    flow_paths = resolve_flow_paths(manifest_path, args.flows, examples_root=examples_root)
    _copy_flow_sources(flow_paths, manifest_path, session_dir)

    wheel_server = str(session_cfg.get("wheel_server") or DEFAULT_WHEEL_SERVER)
    wheel_deploy_dir = Path(str(session_cfg.get("wheel_deploy_dir") or "/tmp/urisys-deploy"))

    meta = _build_meta(
        args.run_id, session_cfg, node_reachable, args, route_map, examples_root, manifest_path, flow_paths
    )
    save_json(session_dir / "meta.json", meta)

    def _run_one(fp: Path) -> dict[str, Any]:
        return run_flow(
            fp,
            endpoint=args.endpoint,
            route_map=route_map,
            session_dir=session_dir,
            wheel_server=wheel_server,
            wheel_deploy_dir=wheel_deploy_dir,
            examples_root=examples_root,
        )

    flow_records, node_reachable = _run_flows(
        flow_paths,
        _run_one=_run_one,
        endpoint=args.endpoint,
        node_reachable=node_reachable,
        meta=meta,
        log_path=log_path,
        session_dir=session_dir,
        examples_root=examples_root,
    )

    meta["steps"] = _collect_step_summaries(meta, flow_records)
    meta["finished_at"] = now_iso()
    meta["flows_ok"] = sum(1 for r in flow_records if r.get("ok"))
    meta["flows_total"] = len(flow_records)
    save_json(session_dir / "meta.json", meta)
    write_session_md(session_dir, meta, flow_records)

    report_script = ROOT / "scripts" / "session_report.py"
    if report_script.exists():
        subprocess.run([sys.executable, str(report_script), "generate", str(session_dir)], check=False)

    return _session_result(node_reachable, flow_records, wheel_proc, log_path, session_dir, meta)


if __name__ == "__main__":
    raise SystemExit(main())
