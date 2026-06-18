from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from ..paths import REPORT_SCRIPT, TELLMESH_ROOT, URISYS_ROOT
from .util import (
    compose_cmd,
    copy_container_file,
    docker_logs,
    finalize_session,
    host_id,
    http_json,
    now_iso,
    prepare_urirdp_data,
    run_cmd,
    save_json,
    sleep_ports,
    wait_health,
    write_meta,
)

ROOT = URISYS_ROOT
TELLMESH = TELLMESH_ROOT

def session_pytest_urirdp(session_dir: Path) -> int:
    started = now_iso()
    write_meta(
        session_dir,
        session_id=session_dir.name,
        session_name="pytest-urirdp",
        suite="unit",
        started_at=started,
        host=host_id(),
    )
    log = session_dir / "session.log"
    pkg = TELLMESH / "urirdp-docker"
    proc = run_cmd([sys.executable, "-m", "pytest", "-q"], cwd=pkg, log_file=log)
    steps = [{"name": "pytest", "status": "pass" if proc.returncode == 0 else "fail", "detail": proc.stderr[-500:] if proc.returncode else ""}]
    return finalize_session(session_dir, started, proc.returncode, steps)


def session_pytest_urisys(session_dir: Path) -> int:
    started = now_iso()
    write_meta(session_dir, session_id=session_dir.name, session_name="pytest-urisys", suite="unit", started_at=started, host=host_id())
    log = session_dir / "session.log"
    proc = run_cmd([sys.executable, "-m", "pytest", "tests/", "-q"], cwd=ROOT, log_file=log)
    steps = [{"name": "pytest", "status": "pass" if proc.returncode == 0 else "fail"}]
    return finalize_session(session_dir, started, proc.returncode, steps)


def session_pytest_urisys_node(session_dir: Path) -> int:
    started = now_iso()
    write_meta(session_dir, session_id=session_dir.name, session_name="pytest-urisys-node", suite="unit", started_at=started, host=host_id())
    log = session_dir / "session.log"
    pkg = TELLMESH / "urisys-node"
    proc = run_cmd([sys.executable, "-m", "pytest", "-q"], cwd=pkg, log_file=log)
    steps = [{"name": "pytest", "status": "pass" if proc.returncode == 0 else "fail"}]
    return finalize_session(session_dir, started, proc.returncode, steps)


def session_urirdp_mock_docker(session_dir: Path) -> int:
    started = now_iso()
    port = 8795
    pkg = TELLMESH / "urirdp-docker"
    write_meta(
        session_dir,
        session_id=session_dir.name,
        session_name="urirdp-mock-docker",
        suite="docker-smoke",
        started_at=started,
        host=host_id(),
        ports={"uri": port},
    )
    log = session_dir / "session.log"
    steps: list[dict[str, Any]] = []
    code = 0

    prepare_urirdp_data(pkg)
    sleep_ports()
    run_cmd(compose_cmd("down", "-v"), cwd=pkg, log_file=log)
    up = run_cmd(compose_cmd("up", "-d", "--build", "urirdp"), cwd=pkg, log_file=log)
    if up.returncode != 0:
        steps.append({"name": "compose-up", "status": "fail"})
        docker_logs("urirdp", None, pkg, session_dir / "docker-logs.txt")
        return finalize_session(session_dir, started, up.returncode, steps)

    try:
        health = wait_health(f"http://127.0.0.1:{port}/health")
        save_json(session_dir / "responses" / "01-health.json", health)
        steps.append({"name": "health", "status": "pass", "uri": f"http://127.0.0.1:{port}/health"})
        time.sleep(3)

        routes = http_json("GET", f"http://127.0.0.1:{port}/uri/routes")
        save_json(session_dir / "responses" / "02-routes.json", routes)
        steps.append({"name": "routes", "status": "pass"})

        click = http_json(
            "POST",
            f"http://127.0.0.1:{port}/uri/call",
            {
                "uri": "kvm://local/task/command/click-text",
                "payload": {"text": "OK"},
                "context": {"approved": True, "dry_run": True},
            },
        )
        save_json(session_dir / "responses" / "03-click-dry-run.json", click)
        steps.append(
            {
                "name": "click-dry-run",
                "status": "pass" if click.get("ok") else "fail",
                "uri": "kvm://local/task/command/click-text",
                "metrics": {"dry_run": True},
            }
        )
        if not click.get("ok"):
            code = 1
    except Exception as exc:
        steps.append({"name": "mock-smoke", "status": "fail", "detail": str(exc)})
        code = 1
    finally:
        docker_logs("urirdp", None, pkg, session_dir / "docker-logs.txt")
        copy_container_file("urirdp-gui", "/opt/urirdp/data/events.jsonl", session_dir / "events.jsonl")
        run_cmd(compose_cmd("down", "-v"), cwd=pkg, log_file=log)

    return finalize_session(session_dir, started, code, steps)


def _record_health(
    session_dir: Path,
    steps: list[dict[str, Any]],
    seq: int,
    name: str,
    url: str,
    attempts: int = 30,
) -> dict[str, Any]:
    health = wait_health(url, attempts=attempts)
    save_json(session_dir / "responses" / f"{seq:02d}-{name}.json", health)
    steps.append({"name": name, "status": "pass"})
    return health


def _bootstrap_rdp(
    container: str,
    log: Path,
    steps: list[dict[str, Any]],
    raise_on_fail: bool = False,
) -> subprocess.CompletedProcess:
    boot = run_cmd(
        ["docker", "exec", container, "bash", "/opt/urirdp/docker/bootstrap-rdp-session.sh"],
        log_file=log,
    )
    steps.append({"name": "bootstrap-rdp", "status": "pass" if boot.returncode == 0 else "fail"})
    if raise_on_fail and boot.returncode != 0:
        raise RuntimeError("bootstrap-rdp-session failed")
    return boot


def _read_display_env(container: str) -> tuple[str, str]:
    disp_proc = run_cmd(
        ["docker", "exec", container, "bash", "-lc", "grep ^DISPLAY= /tmp/urirdp-display.env | cut -d= -f2"],
    )
    display = (disp_proc.stdout or ":10").strip() or ":10"
    xauth_proc = run_cmd(
        ["docker", "exec", container, "bash", "-lc", "grep ^XAUTHORITY= /tmp/urirdp-display.env | cut -d= -f2"],
    )
    xauth = (xauth_proc.stdout or "").strip()
    return display, xauth


def _call_and_record(
    session_dir: Path,
    steps: list[dict[str, Any]],
    seq: int,
    name: str,
    uri: str,
    payload: dict[str, Any] | None = None,
    ctx: dict[str, Any] | None = None,
    timeout: float = 120.0,
    port: int = 8795,
    step_name: str | None = None,
) -> dict[str, Any]:
    resp = http_json(
        "POST",
        f"http://127.0.0.1:{port}/uri/call",
        {"uri": uri, "payload": payload or {}, "context": ctx or {}},
        timeout=timeout,
    )
    save_json(session_dir / "responses" / f"{seq:02d}-{name}.json", resp)
    steps.append({"name": step_name or name, "status": "pass" if resp.get("ok") else "fail"})
    return resp


def _session_compose_up(
    pkg: Path, log: Path, env: dict[str, str], steps: list[dict[str, Any]]
) -> int | None:
    run_cmd(compose_cmd("down", "-v"), cwd=pkg, log_file=log, env=env)
    up = run_cmd(compose_cmd("up", "-d", "--build", "urirdp"), cwd=pkg, log_file=log, env=env)
    if up.returncode != 0:
        steps.append({"name": "compose-up", "status": "fail"})
        return up.returncode
    return None


def _record_screenshot_step(
    session_dir: Path, steps: list[dict[str, Any]], seq: int, port: int, ctx: dict[str, Any], container: str
) -> None:
    shot = _call_and_record(session_dir, steps, seq, "screenshot", "kvm://local/monitor/primary/query/screenshot", {}, ctx, port=port)
    copy_container_file(container, "/opt/urirdp/data/screenshots/latest.png", session_dir / "screenshots" / f"{seq:02d}-screenshot.png")
    captured = (shot.get("result") or {}).get("captured")
    steps[-1].update({
        "uri": "kvm://local/monitor/primary/query/screenshot",
        "status": "pass" if shot.get("ok") and captured else "fail",
        "metrics": {"captured": captured, "driver": (shot.get("result") or {}).get("driver")},
        "screenshot": f"screenshots/{seq:02d}-screenshot.png" if captured else None,
    })


def _record_ocr_step(
    session_dir: Path, steps: list[dict[str, Any]], seq: int, port: int, ctx: dict[str, Any]
) -> None:
    ocr = _call_and_record(session_dir, steps, seq, "ocr", "ocr://local/image/latest/query/text", {}, ctx, port=port)
    text = ((ocr.get("result") or {}).get("text") or "").upper()
    has_ok = "OK" in text
    steps[-1].update({
        "uri": "ocr://local/image/latest/query/text",
        "status": "pass" if ocr.get("ok") and has_ok else "fail",
        "metrics": {"engine": (ocr.get("result") or {}).get("engine"), "has_ok": has_ok},
    })


def _record_click_step(
    session_dir: Path, steps: list[dict[str, Any]], seq: int, port: int, ctx: dict[str, Any], container: str
) -> None:
    click = _call_and_record(session_dir, steps, seq, "click-text", "kvm://local/task/command/click-text", {"text": "OK"}, ctx, timeout=180.0, port=port)
    copy_container_file(container, "/opt/urirdp/data/screenshots/latest.png", session_dir / "screenshots" / f"{seq:02d}-after-click.png")
    result = click.get("result") or {}
    clicked = result.get("clicked")
    driver = (result.get("click") or {}).get("driver")
    steps[-1].update({
        "uri": "kvm://local/task/command/click-text",
        "status": "pass" if click.get("ok") and clicked and driver == "xdotool" else "fail",
        "metrics": {"clicked": clicked, "driver": driver, "reason": (result.get("llm") or {}).get("reason")},
        "screenshot": f"screenshots/{seq:02d}-after-click.png",
    })


def _record_flow_step(session_dir: Path, steps: list[dict[str, Any]], seq: int, container: str, display: str, log: Path) -> None:
    flow = run_cmd(
        [
            "docker", "exec", "-e", "URISYS_ALLOW_REAL=1", container,
            "urisys-rdp", "--config", "/opt/urirdp/config/rdp-kvm-profile.json",
            "flow", "/opt/urirdp/flows/real-rdp-click-text.uri.flow.yaml",
            "--approve", "--allow-real", "--display", display,
        ],
        log_file=log,
    )
    flow_steps = json.loads(flow.stdout) if flow.stdout.strip().startswith("[") else []
    save_json(session_dir / "responses" / f"{seq:02d}-flow.json", flow_steps)
    flow_ok = flow.returncode == 0 and all(s.get("ok") for s in flow_steps)
    steps.append({"name": "flow", "status": "pass" if flow_ok else "fail", "metrics": {"steps": len(flow_steps)}})


def session_urirdp_real_docker(session_dir: Path) -> int:
    started = now_iso()
    port = 8795
    pkg = TELLMESH / "urirdp-docker"
    container = "urirdp-gui"
    write_meta(
        session_dir,
        session_id=session_dir.name,
        session_name="urirdp-real-docker",
        suite="docker-real",
        started_at=started,
        host=host_id(),
        ports={"uri": port, "rdp": 3389},
    )
    log = session_dir / "session.log"
    steps: list[dict[str, Any]] = []

    env = {"URISYS_ALLOW_REAL": "1"}
    prepare_urirdp_data(pkg)
    sleep_ports()
    fail_code = _session_compose_up(pkg, log, env, steps)
    if fail_code is not None:
        return finalize_session(session_dir, started, fail_code, steps)

    try:
        _record_health(session_dir, steps, 1, "health", f"http://127.0.0.1:{port}/health")
        time.sleep(5)
        _bootstrap_rdp(container, log, steps, raise_on_fail=True)

        display, xauth = _read_display_env(container)
        write_meta(session_dir, display=display, xauthority=xauth)
        ctx = {"approved": True, "allow_real": True, "display": display, "xauthority": xauth}

        _record_screenshot_step(session_dir, steps, 2, port, ctx, container)
        _record_ocr_step(session_dir, steps, 3, port, ctx)
        _record_click_step(session_dir, steps, 4, port, ctx, container)
        _record_flow_step(session_dir, steps, 5, container, display, log)

        code = 1 if any(s["status"] == "fail" for s in steps) else 0
    except Exception as exc:
        steps.append({"name": "real-docker", "status": "fail", "detail": str(exc)})
        code = 1
    finally:
        docker_logs("urirdp", None, pkg, session_dir / "docker-logs.txt")
        copy_container_file(container, "/opt/urirdp/data/events.jsonl", session_dir / "events.jsonl")
        run_cmd(compose_cmd("down", "-v"), cwd=pkg, log_file=log)

    return finalize_session(session_dir, started, code, steps)


def session_urirdp_rdp_e2e(session_dir: Path) -> int:
    started = now_iso()
    pkg = TELLMESH / "urirdp-docker"
    compose = pkg / "docker-compose.rdp-e2e.yml"
    write_meta(
        session_dir,
        session_id=session_dir.name,
        session_name="urirdp-rdp-e2e",
        suite="docker-e2e",
        started_at=started,
        host=host_id(),
        ports={"uri": 8795, "rdp": 3389},
    )
    log = session_dir / "session.log"
    steps: list[dict[str, Any]] = []

    prepare_urirdp_data(pkg)
    sleep_ports()
    run_cmd(compose_cmd("down", "-v", compose_file=compose), cwd=pkg, log_file=log)
    proc = run_cmd(
        compose_cmd(
            "up",
            "--build",
            "--abort-on-container-exit",
            "--exit-code-from",
            "rdp-client",
            compose_file=compose,
        ),
        cwd=pkg,
        log_file=log,
        timeout=600.0,
    )
    docker_logs("urirdp", compose, pkg, session_dir / "docker-logs-urirdp.txt")
    docker_logs("rdp-client", compose, pkg, session_dir / "docker-logs-rdp-client.txt")
    copy_container_file("urirdp-real", "/opt/urirdp/data/events.jsonl", session_dir / "events.jsonl")
    copy_container_file("urirdp-real", "/opt/urirdp/data/screenshots/latest.png", session_dir / "screenshots" / "e2e-latest.png")

    if "ALL PASSED" in (proc.stdout or "") + (proc.stderr or ""):
        steps.append({"name": "e2e-rdp-real", "status": "pass"})
    else:
        steps.append({"name": "e2e-rdp-real", "status": "fail", "detail": (proc.stderr or proc.stdout)[-500:]})

    run_cmd(compose_cmd("down", "-v", compose_file=compose), cwd=pkg, log_file=log)
    sleep_ports()
    return finalize_session(session_dir, started, proc.returncode, steps)


def session_automation_lab(session_dir: Path, *, use_existing: bool = False) -> int:
    started = now_iso()
    lab = TELLMESH / "urisys-automation-lab"
    lab_port = 8099
    rdp_port = 8795
    write_meta(
        session_dir,
        session_id=session_dir.name,
        session_name="automation-lab",
        suite="lab-stack",
        started_at=started,
        host=host_id(),
        ports={"lab": lab_port, "uri": rdp_port},
    )
    log = session_dir / "session.log"
    steps: list[dict[str, Any]] = []
    code = 0

    if not use_existing:
        sleep_ports()
        run_cmd(["bash", "scripts/docker-down.sh"], cwd=lab, log_file=log)
        up = run_cmd(["bash", "scripts/docker-up.sh"], cwd=lab, log_file=log, timeout=600.0)
        if up.returncode != 0:
            steps.append({"name": "lab-up", "status": "fail"})
            return finalize_session(session_dir, started, up.returncode, steps)

    try:
        _record_health(session_dir, steps, 1, "lab-health", f"http://127.0.0.1:{lab_port}/health", attempts=60)
        _record_health(session_dir, steps, 2, "rdp-health", f"http://127.0.0.1:{rdp_port}/health", attempts=60)

        stt = _call_and_record(session_dir, steps, 3, "stt", "stt://local/session/main/query/transcript", {"text": "kliknij OK"}, {"approved": True}, port=lab_port, step_name="stt-mock")
        steps[-1]["uri"] = stt.get("uri")

        chat_dry = _call_and_record(session_dir, steps, 4, "chat-dry-run", "chat://local/uri/command/execute", {"transcript": "kliknij OK", "dry_run": True, "approved": True}, {"approved": True, "dry_run": True}, port=lab_port)

        _bootstrap_rdp("urisys-lab-urirdp", log, steps)

        chat_real = _call_and_record(session_dir, steps, 5, "chat-real", "chat://local/uri/command/execute", {"transcript": "kliknij OK", "approved": True}, {"approved": True, "allow_real": True}, timeout=180.0, port=lab_port, step_name="chat-real-forward")
        copy_container_file("urisys-lab-urirdp", "/opt/urirdp/data/screenshots/latest.png", session_dir / "screenshots" / "05-lab-real-click.png")
        inner = ((chat_real.get("result") or {}).get("result") or {}).get("result") or {}
        clicked = inner.get("clicked")
        steps[-1].update({
            "status": "pass" if chat_real.get("ok") and clicked else "fail",
            "uri": "chat://local/uri/command/execute",
            "metrics": {"clicked": clicked},
            "screenshot": "screenshots/05-lab-real-click.png" if clicked else None,
        })

        if any(s["status"] == "fail" for s in steps):
            code = 1
    except Exception as exc:
        steps.append({"name": "automation-lab", "status": "fail", "detail": str(exc)})
        code = 1
    finally:
        docker_logs("urirdp", lab / "docker-compose.lab.yml", lab, session_dir / "docker-logs-urirdp.txt")
        docker_logs("automation-lab", lab / "docker-compose.lab.yml", lab, session_dir / "docker-logs-lab.txt")
        copy_container_file("urisys-lab-urirdp", "/opt/urirdp/data/events.jsonl", session_dir / "events-urirdp.jsonl")
        lab_events = lab / "data" / "events.jsonl"
        if lab_events.is_file():
            shutil.copy2(lab_events, session_dir / "events-lab.jsonl")

    return finalize_session(session_dir, started, code, steps)


def _monorepo_root() -> Path | None:
    candidate = ROOT.parent
    if (candidate / "uricore").is_dir() and (TELLMESH / "urisys-automation-lab").is_dir():
        return candidate
    if (ROOT / "uricore").is_dir():
        return ROOT
    return None


def session_urisys_node_docker_gui(session_dir: Path) -> int:
    started = now_iso()
    port = int(os.environ.get("URISYS_NODE_HOST_PORT", "8790"))
    write_meta(
        session_dir,
        session_id=session_dir.name,
        session_name="urisys-node-docker-gui",
        suite="docker-gui",
        started_at=started,
        host=host_id(),
        ports={"node": port},
    )
    log = session_dir / "session.log"
    steps: list[dict[str, Any]] = []
    code = 0

    if _monorepo_root() is None:
        steps.append(
            {
                "name": "preflight-monorepo",
                "status": "fail",
                "detail": "uricore sibling missing — run from tellmesh checkout (urisys + uricore)",
            }
        )
        return finalize_session(session_dir, started, 1, steps)

    env = os.environ.copy()
    env["URISYS_NODE_E2E_KEEP"] = "0"
    env["URISYS_NODE_SESSION_DIR"] = str(session_dir)
    proc = run_cmd(
        ["bash", "scripts/run-urisys-node-docker-e2e.sh"],
        cwd=ROOT,
        log_file=log,
        timeout=600.0,
        env=env,
    )
    steps.append(
        {
            "name": "host-control-e2e",
            "status": "pass" if proc.returncode == 0 else "fail",
            "detail": "" if proc.returncode == 0 else (proc.stderr or proc.stdout or "")[-500:],
        }
    )
    if proc.returncode != 0:
        code = 1
    return finalize_session(session_dir, started, code, steps)


def session_office_simulate(session_dir: Path) -> int:
    started = now_iso()
    port = int(os.environ.get("URISYS_NODE_HOST_PORT", "8790"))
    write_meta(
        session_dir,
        session_id=session_dir.name,
        session_name="office-simulate",
        suite="docker-gui",
        started_at=started,
        host=host_id(),
        ports={"node": port},
    )
    log = session_dir / "session.log"
    steps: list[dict[str, Any]] = []
    code = 0

    if _monorepo_root() is None:
        steps.append(
            {
                "name": "preflight-monorepo",
                "status": "fail",
                "detail": "uricore sibling missing — run from tellmesh checkout",
            }
        )
        return finalize_session(session_dir, started, 1, steps)

    env = os.environ.copy()
    env["URISYS_OFFICE_E2E_KEEP"] = "0"
    env["URISYS_OFFICE_SESSION_DIR"] = str(session_dir)
    proc = run_cmd(
        ["bash", "scripts/run-office-simulate-e2e.sh"],
        cwd=ROOT,
        log_file=log,
        timeout=900.0,
        env=env,
    )
    steps.append(
        {
            "name": "office-simulate-e2e",
            "status": "pass" if proc.returncode == 0 else "fail",
            "detail": "" if proc.returncode == 0 else (proc.stderr or proc.stdout or "")[-800:],
        }
    )
    if proc.returncode != 0:
        code = 1
    return finalize_session(session_dir, started, code, steps)


def session_office_simulate_lenovo(session_dir: Path) -> int:
    started = now_iso()
    base = os.environ.get("LENOVO", "http://192.168.188.201:8790")
    write_meta(
        session_dir,
        session_id=session_dir.name,
        session_name="office-simulate-lenovo",
        suite="remote-node",
        started_at=started,
        host=host_id(),
        ports={"node": base.rsplit(":", 1)[-1] if ":" in base else "8790"},
        extra={"target": base},
    )
    log = session_dir / "session.log"
    steps: list[dict[str, Any]] = []
    env = os.environ.copy()
    env["OFFICE_LENOVO_SESSION_DIR"] = str(session_dir)
    env["LENOVO"] = base
    proc = run_cmd(
        ["bash", "scripts/run-office-simulate-lenovo.sh"],
        cwd=ROOT,
        log_file=log,
        timeout=900.0,
        env=env,
    )
    steps.append(
        {
            "name": "office-simulate-lenovo",
            "status": "pass" if proc.returncode == 0 else "fail",
            "detail": "" if proc.returncode == 0 else (proc.stderr or proc.stdout or "")[-800:],
        }
    )
    return finalize_session(session_dir, started, proc.returncode, steps)


def session_office_writer(session_dir: Path) -> int:
    started = now_iso()
    port = int(os.environ.get("URISYS_NODE_HOST_PORT", "8790"))
    write_meta(
        session_dir,
        session_id=session_dir.name,
        session_name="office-writer",
        suite="docker-gui",
        started_at=started,
        host=host_id(),
        ports={"node": port},
    )
    log = session_dir / "session.log"
    steps: list[dict[str, Any]] = []
    code = 0

    if _monorepo_root() is None:
        steps.append(
            {
                "name": "preflight-monorepo",
                "status": "fail",
                "detail": "uricore sibling missing — run from tellmesh checkout",
            }
        )
        return finalize_session(session_dir, started, 1, steps)

    env = os.environ.copy()
    env["URISYS_OFFICE_E2E_KEEP"] = "0"
    env["URISYS_OFFICE_WRITER_SESSION_DIR"] = str(session_dir)
    proc = run_cmd(
        ["bash", "scripts/run-office-writer-e2e.sh"],
        cwd=ROOT,
        log_file=log,
        timeout=900.0,
        env=env,
    )
    steps.append(
        {
            "name": "office-writer-e2e",
            "status": "pass" if proc.returncode == 0 else "fail",
            "detail": "" if proc.returncode == 0 else (proc.stderr or proc.stdout or "")[-800:],
        }
    )
    if proc.returncode != 0:
        code = 1
    return finalize_session(session_dir, started, code, steps)


def session_email_mailpit(session_dir: Path) -> int:
    started = now_iso()
    port = int(os.environ.get("URISYS_NODE_HOST_PORT", "8790"))
    write_meta(
        session_dir,
        session_id=session_dir.name,
        session_name="email-mailpit",
        suite="docker-gui",
        started_at=started,
        host=host_id(),
        ports={"node": port, "mailpit_ui": 8025, "mailpit_smtp": 1025},
    )
    log = session_dir / "session.log"
    steps: list[dict[str, Any]] = []
    code = 0

    if _monorepo_root() is None:
        steps.append(
            {
                "name": "preflight-monorepo",
                "status": "fail",
                "detail": "uricore sibling missing — run from tellmesh checkout",
            }
        )
        return finalize_session(session_dir, started, 1, steps)

    env = os.environ.copy()
    env["URISYS_OFFICE_E2E_KEEP"] = "0"
    env["URISYS_EMAIL_MAILPIT_SESSION_DIR"] = str(session_dir)
    proc = run_cmd(
        ["bash", "scripts/run-email-mailpit-e2e.sh"],
        cwd=ROOT,
        log_file=log,
        timeout=900.0,
        env=env,
    )
    steps.append(
        {
            "name": "email-mailpit-e2e",
            "status": "pass" if proc.returncode == 0 else "fail",
            "detail": "" if proc.returncode == 0 else (proc.stderr or proc.stdout or "")[-800:],
        }
    )
    if proc.returncode != 0:
        code = 1
    return finalize_session(session_dir, started, code, steps)

