"""Filesystem anchors for urisys lab runners (tellmesh monorepo layout)."""

from __future__ import annotations

from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[2]
TELLMESH_ROOT = LAB_ROOT.parent
URISYS_ROOT = TELLMESH_ROOT / "urisys"
NODE_ROOT = TELLMESH_ROOT / "urisys-node"
REPORT_SCRIPT = URISYS_ROOT / "scripts" / "session_report.py"
