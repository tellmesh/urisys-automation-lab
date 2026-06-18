from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core import host_id, now_iso, save_json
from ..paths import REPORT_SCRIPT, TELLMESH_ROOT, URISYS_ROOT

ROOT = URISYS_ROOT
TELLMESH = TELLMESH_ROOT


def run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def http_json(
    method: str,
    url: str,
    body: dict | None = None,
    timeout: float = 120.0,
    *,
    retries: int = 5,
    retry_delay: float = 2.0,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    last_err = ""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                last_err = raw or str(exc)
                if attempt + 1 < retries:
                    time.sleep(retry_delay)
                    continue
                raise RuntimeError(f"HTTP {method} {url} failed: {last_err}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ConnectionResetError) as exc:
            last_err = str(exc)
            if attempt + 1 < retries:
                time.sleep(retry_delay)
                continue
            raise RuntimeError(f"HTTP {method} {url} failed: {last_err}") from exc
    raise RuntimeError(f"HTTP {method} {url} failed: {last_err}")


def wait_health(url: str, attempts: int = 90, delay: float = 1.0) -> dict[str, Any]:
    last_err = ""
    for _ in range(attempts):
        try:
            return http_json("GET", url, retries=3, retry_delay=1.0)
        except RuntimeError as exc:
            last_err = str(exc)
            time.sleep(delay)
    raise RuntimeError(f"health timeout for {url}: {last_err}")


def compose_cmd(*parts: str, compose_file: Path | None = None) -> list[str]:
    cmd = ["docker", "compose"]
    if compose_file:
        cmd.extend(["-f", str(compose_file)])
    cmd.extend(parts)
    if parts and parts[0] in {"up", "down"}:
        cmd.append("--remove-orphans")
    return cmd


def run_cmd(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    log_file: Path | None = None,
    timeout: float | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=merged,
    )
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(f"$ {' '.join(cmd)}\n")
            if proc.stdout:
                fh.write(proc.stdout)
            if proc.stderr:
                fh.write("\n--- stderr ---\n")
                fh.write(proc.stderr)
            fh.write(f"\n--- exit {proc.returncode} ---\n")
    return proc


def write_meta(session_dir: Path, **kwargs: Any) -> None:
    meta_path = session_dir / "meta.json"
    meta = read_meta(meta_path)
    meta.update(kwargs)
    save_json(meta_path, meta)


def read_meta(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def finalize_session(session_dir: Path, started_at: str, exit_code: int, steps: list[dict[str, Any]]) -> int:
    finished = now_iso()
    t0 = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    t1 = datetime.fromisoformat(finished.replace("Z", "+00:00"))
    status = "pass" if exit_code == 0 and all(s.get("status") == "pass" for s in steps) else "fail"
    write_meta(
        session_dir,
        finished_at=finished,
        duration_s=max(0.0, (t1 - t0).total_seconds()),
        exit_code=exit_code,
        status=status,
        steps=steps,
    )
    subprocess.run([sys.executable, str(REPORT_SCRIPT), "generate", str(session_dir)], check=False)
    return 0 if status == "pass" else 1


def docker_logs(service: str, compose_file: Path | None, cwd: Path, out: Path) -> None:
    cmd = compose_cmd("logs", "--tail=200", service, compose_file=compose_file)
    proc = run_cmd(cmd, cwd=cwd)
    out.write_text((proc.stdout or "") + (proc.stderr or ""), encoding="utf-8")


def copy_container_file(container: str, src: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["docker", "cp", f"{container}:{src}", str(dest)],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0 and dest.is_file()


def copy_host_screenshot(src: Path, session_dir: Path, name: str) -> str | None:
    if not src.is_file():
        return None
    dest = session_dir / "screenshots" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return str(dest.relative_to(session_dir))


def file_md5(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.md5(path.read_bytes()).hexdigest()


def sleep_ports() -> None:
    time.sleep(3)


def prepare_urirdp_data(pkg: Path) -> None:
    data = pkg / "data"
    data.mkdir(parents=True, exist_ok=True)
    for name in ("events.jsonl", "test-events.jsonl"):
        p = data / name
        if p.is_file():
            p.write_text("", encoding="utf-8")
    shots = data / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    for png in shots.glob("*.png"):
        png.unlink(missing_ok=True)
