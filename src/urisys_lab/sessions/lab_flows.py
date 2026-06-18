from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .expectations import evaluate_expectations, flow_expectations
from .lab_rdp import (
    capture_rdp_screenshot,
    capture_rdp_screenshot_wait,
    parse_docker_log_errors,
)
from .util import (
    ROOT,
    TELLMESH,
    copy_container_file,
    docker_logs,
    file_md5,
    finalize_session,
    host_id,
    http_json,
    now_iso,
    run_cmd,
    save_json,
    sleep_ports,
    wait_health,
    write_meta,
)


def _lab_bootstrap(
    session_dir: Path,
    *,
    container: str,
    log: Path,
) -> tuple[str, str]:
    boot = run_cmd(
        ["docker", "exec", container, "bash", "/opt/urirdp/docker/bootstrap-rdp-session.sh"],
        log_file=log,
    )
    if boot.returncode != 0:
        raise RuntimeError("bootstrap-rdp-session failed")
    disp_proc = run_cmd(
        ["docker", "exec", container, "bash", "-lc", "grep ^DISPLAY= /tmp/urirdp-display.env | cut -d= -f2"],
    )
    display = (disp_proc.stdout or ":10").strip() or ":10"
    xauth_proc = run_cmd(
        ["docker", "exec", container, "bash", "-lc", "grep ^XAUTHORITY= /tmp/urirdp-display.env | cut -d= -f2"],
    )
    xauth = (xauth_proc.stdout or "").strip()
    write_meta(session_dir, display=display, xauthority=xauth)
    return display, xauth


def _capture_flow_screenshot(
    session_dir: Path,
    *,
    expect: dict[str, Any],
    flow_id: str,
    idx: int,
    rdp_port: int,
    display: str,
    xauth: str,
    container: str,
    screenshot_hashes: dict[str, str],
) -> tuple[bool, str | None, str | None, str | None]:
    if expect.get("screen_changed_since_previous"):
        time.sleep(5.0)
    elif expect.get("screen_changed") or "browser" in flow_id or "gui" in flow_id:
        time.sleep(3.0)
    png_name = f"{idx:02d}-{flow_id}.png"
    avoid = {digest for digest in screenshot_hashes.values() if digest}
    if expect.get("screen_changed") and avoid:
        captured, shot_rel = capture_rdp_screenshot_wait(
            session_dir,
            rdp_port=rdp_port,
            display=display,
            xauth=xauth,
            container=container,
            filename=png_name,
            avoid_md5s=avoid,
        )
    else:
        captured, shot_rel = capture_rdp_screenshot(
            session_dir,
            rdp_port=rdp_port,
            display=display,
            xauth=xauth,
            container=container,
            filename=png_name,
        )
    png_md5 = file_md5(session_dir / shot_rel) if shot_rel else None
    duplicate_of: str | None = None
    if png_md5:
        for label, digest in screenshot_hashes.items():
            if digest == png_md5:
                duplicate_of = label
                break
        screenshot_hashes[f"{idx:02d}-{flow_id}"] = png_md5
    return captured, shot_rel, png_md5, duplicate_of


def _flow_step_detail(
    *,
    transport_ok: bool,
    flow_pass: bool,
    expect_failures: list[str],
    flow_result: dict[str, Any],
    steps_ok: int,
    steps_total: int,
    duplicate_of: str | None,
) -> str:
    if transport_ok and expect_failures:
        return "; ".join(expect_failures)
    if flow_pass:
        return ""
    return f"{steps_ok}/{steps_total} ok, flow_ok={flow_result.get('ok')}, dup={duplicate_of}"


def _run_single_lab_flow(
    session_dir: Path,
    *,
    idx: int,
    flow_path: Path,
    lab_port: int,
    rdp_port: int,
    display: str,
    xauth: str,
    container: str,
    screenshot_hashes: dict[str, str],
    baseline_md5: str | None,
    prev_md5: str | None,
) -> tuple[dict[str, Any], bool, str | None]:
    flow_id = flow_path.stem
    container_flow = f"/opt/lab/flows/{flow_path.name}"
    flow_ctx = {
        "approved": True,
        "allow_real": True,
        "dry_run": False,
        "display": display,
        "xauthority": xauth,
    }
    try:
        flow_result = http_json(
            "POST",
            f"http://127.0.0.1:{lab_port}/uri/flow",
            {"path": container_flow, "context": flow_ctx},
            timeout=600.0,
        )
    except Exception as exc:
        flow_result = {"ok": False, "error": str(exc), "steps": []}

    step_results = flow_result.get("steps") or []
    steps_ok = sum(1 for s in step_results if s.get("ok"))
    steps_total = len(step_results)
    expect = flow_expectations(flow_path)

    captured, shot_rel, png_md5, duplicate_of = _capture_flow_screenshot(
        session_dir,
        expect=expect,
        flow_id=flow_id,
        idx=idx,
        rdp_port=rdp_port,
        display=display,
        xauth=xauth,
        container=container,
        screenshot_hashes=screenshot_hashes,
    )

    expect_failures = evaluate_expectations(
        expect,
        screenshot_md5=png_md5,
        baseline_md5=baseline_md5,
        previous_md5=prev_md5,
        duplicate_of=duplicate_of,
        step_results=step_results,
    )

    save_json(
        session_dir / "responses" / f"{idx:02d}-{flow_id}.json",
        {
            "flow": flow_id,
            "flow_file": flow_path.name,
            "container_flow": container_flow,
            "real_mode": True,
            "ok": bool(flow_result.get("ok")),
            "flow_id": flow_result.get("flow_id"),
            "description": flow_result.get("description"),
            "graph": flow_result.get("graph"),
            "steps": step_results,
            "error": flow_result.get("error"),
            "screenshot": shot_rel,
            "captured": captured,
            "md5": png_md5,
            "duplicate_of": duplicate_of,
            "expect": expect,
            "expect_failures": expect_failures,
        },
    )

    transport_ok = bool(flow_result.get("ok")) and steps_ok == steps_total and steps_total > 0
    flow_pass = transport_ok and not expect_failures
    step = {
        "name": flow_id,
        "status": "pass" if flow_pass else "fail",
        "uri": flow_path.name,
        "metrics": {
            "steps_ok": steps_ok,
            "steps_total": steps_total,
            "screenshot": shot_rel,
            "captured": captured,
            "md5": png_md5,
            "duplicate_of": duplicate_of,
            "expect_failures": expect_failures,
        },
        "screenshot": shot_rel,
        "detail": _flow_step_detail(
            transport_ok=transport_ok,
            flow_pass=flow_pass,
            expect_failures=expect_failures,
            flow_result=flow_result,
            steps_ok=steps_ok,
            steps_total=steps_total,
            duplicate_of=duplicate_of,
        ),
    }
    return step, flow_pass, png_md5 or prev_md5


def session_lab_10_flows(session_dir: Path) -> int:
    """Run all 10 automation-lab flows; capture one RDP screenshot per flow."""
    started = now_iso()
    lab = TELLMESH / "urisys-automation-lab"
    flows_dir = lab / "flows"
    lab_port = 8099
    rdp_port = 8795
    container = "urisys-lab-urirdp"
    write_meta(
        session_dir,
        session_id=session_dir.name,
        session_name="lab-10-flows",
        suite="lab-flows",
        started_at=started,
        host=host_id(),
        ports={"lab": lab_port, "uri": rdp_port},
        flow_count=10,
    )
    log = session_dir / "session.log"
    steps: list[dict[str, Any]] = []
    code = 0
    screenshot_hashes: dict[str, str] = {}

    sleep_ports()
    run_cmd(["bash", "scripts/docker-down.sh"], cwd=lab, log_file=log)
    up = run_cmd(["bash", "scripts/docker-up.sh"], cwd=lab, log_file=log, timeout=600.0)
    if up.returncode != 0:
        steps.append({"name": "lab-up", "status": "fail"})
        return finalize_session(session_dir, started, up.returncode, steps)

    try:
        wait_health(f"http://127.0.0.1:{lab_port}/health", attempts=60)
        wait_health(f"http://127.0.0.1:{rdp_port}/health", attempts=60)
        steps.append({"name": "stack-health", "status": "pass"})

        display, xauth = _lab_bootstrap(session_dir, container=container, log=log)
        steps.append({"name": "bootstrap-rdp", "status": "pass"})

        capture_rdp_screenshot(
            session_dir,
            rdp_port=rdp_port,
            display=display,
            xauth=xauth,
            container=container,
            filename="00-baseline.png",
        )
        prev_md5 = file_md5(session_dir / "screenshots" / "00-baseline.png")
        if prev_md5:
            screenshot_hashes["00-baseline"] = prev_md5

        flow_paths = sorted(flows_dir.glob("*.uri.flow.yaml"))
        if len(flow_paths) != 10:
            steps.append(
                {
                    "name": "flow-count",
                    "status": "fail",
                    "detail": f"expected 10 flows, found {len(flow_paths)}",
                }
            )
            code = 1

        for idx, flow_path in enumerate(flow_paths, start=1):
            step, flow_pass, prev_md5 = _run_single_lab_flow(
                session_dir,
                idx=idx,
                flow_path=flow_path,
                lab_port=lab_port,
                rdp_port=rdp_port,
                display=display,
                xauth=xauth,
                container=container,
                screenshot_hashes=screenshot_hashes,
                baseline_md5=screenshot_hashes.get("00-baseline"),
                prev_md5=prev_md5,
            )
            steps.append(step)
            if not flow_pass:
                code = 1

    except Exception as exc:
        steps.append({"name": "lab-10-flows", "status": "fail", "detail": str(exc)})
        code = 1
    finally:
        docker_logs("urirdp", lab / "docker-compose.lab.yml", lab, session_dir / "docker-logs-urirdp.txt")
        docker_logs("automation-lab", lab / "docker-compose.lab.yml", lab, session_dir / "docker-logs-lab.txt")
        copy_container_file(container, "/opt/urirdp/data/events.jsonl", session_dir / "events-urirdp.jsonl")
        log_errors = parse_docker_log_errors(session_dir)
        save_json(session_dir / "log-errors.json", log_errors)
        write_meta(session_dir, log_errors=log_errors, screenshot_hashes=screenshot_hashes)

    return finalize_session(session_dir, started, code, steps)
