from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from ..paths import REPORT_SCRIPT, TELLMESH_ROOT, URISYS_ROOT
from ..core import host_id, now_iso, run_id, save_json
from .runners import (
    session_automation_lab,
    session_email_mailpit,
    session_office_simulate,
    session_office_simulate_lenovo,
    session_office_writer,
    session_pytest_urirdp,
    session_pytest_urisys,
    session_pytest_urisys_node,
    session_urirdp_mock_docker,
    session_urirdp_real_docker,
    session_urirdp_rdp_e2e,
    session_urisys_node_docker_gui,
)
from .lab_flows import session_lab_10_flows
from .util import run_cmd

ROOT = URISYS_ROOT
TELLMESH = TELLMESH_ROOT

SESSIONS: dict[str, Callable[[Path], int]] = {
    "pytest-urirdp": session_pytest_urirdp,
    "pytest-urisys": session_pytest_urisys,
    "pytest-urisys-node": session_pytest_urisys_node,
    "urirdp-mock-docker": session_urirdp_mock_docker,
    "urirdp-real-docker": session_urirdp_real_docker,
    "urirdp-rdp-e2e": session_urirdp_rdp_e2e,
    "automation-lab": session_automation_lab,
    "lab-10-flows": session_lab_10_flows,
    "urisys-node-docker-gui": session_urisys_node_docker_gui,
    "office-simulate": session_office_simulate,
    "office-simulate-lenovo": session_office_simulate_lenovo,
    "office-writer": session_office_writer,
    "email-mailpit": session_email_mailpit,
}

DEFAULT_ORDER = [
    "pytest-urisys",
    "pytest-urirdp",
    "pytest-urisys-node",
    "urirdp-mock-docker",
    "urirdp-real-docker",
    "urirdp-rdp-e2e",
    "automation-lab",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run urisys test sessions with reports")
    parser.add_argument("--output", type=Path, default=ROOT / "output" / "test-sessions")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--sessions", default="", help="Comma-separated session names")
    parser.add_argument("--keep-lab", action="store_true", help="Leave automation-lab stack running")
    args = parser.parse_args()

    run_dir = args.output / (args.run_id or run_id())
    run_dir.mkdir(parents=True, exist_ok=True)

    names = [s.strip() for s in args.sessions.split(",") if s.strip()] or DEFAULT_ORDER
    manifest = {"run_id": run_dir.name, "started_at": now_iso(), "host": host_id(), "sessions": names}
    save_json(run_dir / "manifest.json", manifest)

    if any(n in names for n in ("urirdp-mock-docker", "urirdp-real-docker", "urirdp-rdp-e2e")):
        lab = TELLMESH / "urisys-automation-lab"
        run_cmd(["bash", "scripts/docker-down.sh"], cwd=lab, log_file=run_dir / "preflight.log")

    results: dict[str, int] = {}
    for name in names:
        if name not in SESSIONS:
            print(f"unknown session: {name}", file=sys.stderr)
            results[name] = 1
            continue
        session_dir = run_dir / name
        session_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n=== session: {name} -> {session_dir} ===")
        t0 = time.time()
        if name == "automation-lab":
            rc = session_automation_lab(session_dir, use_existing=False)
        else:
            rc = SESSIONS[name](session_dir)
        results[name] = rc
        print(f"=== {name}: {'PASS' if rc == 0 else 'FAIL'} ({time.time() - t0:.1f}s) ===")

    manifest["finished_at"] = now_iso()
    manifest["results"] = results
    save_json(run_dir / "manifest.json", manifest)

    subprocess.run([sys.executable, str(REPORT_SCRIPT), "analyze", str(run_dir)], check=False)
    print(f"\nRun directory: {run_dir}")
    print(f"Analysis: {run_dir / 'analysis.md'}")
    return 0 if all(rc == 0 for rc in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
