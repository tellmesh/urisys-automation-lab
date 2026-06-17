"""Lab tests for the effect-level `expect:` flow contracts (Docker-free).

Locks in two things the transport-only pass/fail gate cannot:
  1. every flow's declared `expect:` block is well-formed, and
  2. `evaluate_expectations` actually asserts the declared effect.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

LAB = Path(__file__).resolve().parents[1]
ROOT = LAB.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import run_test_sessions as R  # noqa: E402
import session_report as SR  # noqa: E402

FLOWS_DIR = LAB / "flows"
FLOW_FILES = sorted(FLOWS_DIR.glob("*.uri.flow.yaml"))

# Keys understood by evaluate_expectations; anything else is a typo/contract drift.
KNOWN_EXPECT_KEYS = {
    "screen_changed",
    "screen_changed_since_previous",
    "opened_url_contains",
    "ocr_contains",
    "min_vision_confidence",
}


def test_flow_files_exist():
    assert FLOW_FILES, f"no flow files found under {FLOWS_DIR}"


@pytest.mark.parametrize("flow_path", FLOW_FILES, ids=lambda p: p.stem)
def test_expect_block_is_well_formed(flow_path: Path):
    """An `expect:` block, if present, must only use known keys with valid types."""
    expect = R._flow_expectations(flow_path)
    assert isinstance(expect, dict)
    unknown = set(expect) - KNOWN_EXPECT_KEYS
    assert not unknown, f"{flow_path.name}: unknown expect keys {unknown}"
    if "screen_changed" in expect:
        assert isinstance(expect["screen_changed"], bool)
    if "screen_changed_since_previous" in expect:
        assert isinstance(expect["screen_changed_since_previous"], bool)
    if "opened_url_contains" in expect:
        assert isinstance(expect["opened_url_contains"], str)
    if "ocr_contains" in expect:
        assert isinstance(expect["ocr_contains"], list)
        assert all(isinstance(s, str) for s in expect["ocr_contains"])
    if "min_vision_confidence" in expect:
        assert isinstance(expect["min_vision_confidence"], (int, float))
        assert 0.0 <= float(expect["min_vision_confidence"]) <= 1.0


@pytest.mark.parametrize("flow_path", FLOW_FILES, ids=lambda p: p.stem)
def test_flow_still_parses_with_expect(flow_path: Path):
    """`expect:` is a sibling of `do:` — the flow document must stay valid."""
    data = yaml.safe_load(flow_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert isinstance(data.get("flow"), dict)
    assert isinstance(data.get("do"), list) and data["do"]


def test_evaluate_screen_changed():
    ok = R.evaluate_expectations(
        {"screen_changed": True},
        screenshot_md5="bbbb",
        baseline_md5="aaaa",
        duplicate_of="02-other",
        step_results=[],
    )
    bad = R.evaluate_expectations(
        {"screen_changed": True},
        screenshot_md5="aaaa",
        baseline_md5="aaaa",
        duplicate_of="00-baseline",
        step_results=[],
    )
    assert ok == []
    assert bad and "screen_changed" in bad[0]


def test_evaluate_screen_changed_since_previous():
    ok = R.evaluate_expectations(
        {"screen_changed_since_previous": True},
        screenshot_md5="cccc",
        previous_md5="bbbb",
        step_results=[],
    )
    bad = R.evaluate_expectations(
        {"screen_changed_since_previous": True},
        screenshot_md5="bbbb",
        previous_md5="bbbb",
        duplicate_of="03-flow",
        step_results=[],
    )
    assert ok == []
    assert bad and "screen_changed_since_previous" in bad[0]


def test_evaluate_ocr_contains():
    step = {"response": {"result": {"result": {"text": "File System Home"}}}}
    assert R.evaluate_expectations({"ocr_contains": ["Home"]}, duplicate_of=None, step_results=[step]) == []
    miss = R.evaluate_expectations({"ocr_contains": ["Submit"]}, duplicate_of=None, step_results=[step])
    assert miss and "Submit" in miss[0]


def test_evaluate_min_vision_confidence():
    dead = {"response": {"result": {"model": "x", "action": "none", "confidence": 0.0}}}
    live = {"response": {"result": {"model": "x", "action": "click", "confidence": 0.8}}}
    assert R.evaluate_expectations({"min_vision_confidence": 0.3}, duplicate_of=None, step_results=[dead])
    assert R.evaluate_expectations({"min_vision_confidence": 0.3}, duplicate_of=None, step_results=[live]) == []


def test_no_expect_is_transport_only():
    assert R.evaluate_expectations({}, duplicate_of="00-baseline", step_results=[]) == []


def test_evaluate_opened_url_contains():
    steps = [
        {
            "response": {
                "result": {
                    "url": "https://raw.githubusercontent.com/github/markup/master/README.md",
                    "driver": "display-chromium",
                }
            }
        }
    ]
    assert (
        R.evaluate_expectations({"opened_url_contains": "github/markup"}, step_results=steps)
        == []
    )
    miss = R.evaluate_expectations({"opened_url_contains": "example.com"}, step_results=steps)
    assert miss and "opened_url_contains" in miss[0]


def test_analyzer_reports_duplicate_screenshots():
    outcomes = [
        SR.FlowOutcome(flow="04_browser", is_gui=True, duplicate_of="03_browser", has_contract=True),
        SR.FlowOutcome(flow="01_shell", is_gui=False, duplicate_of=SR.BASELINE_LABEL, has_contract=False),
    ]
    dup_codes = [f.code for f in SR.check_duplicate_screenshots(outcomes)]
    shell_codes = [f.code for f in SR.check_shell_baseline_duplicate(outcomes)]
    assert dup_codes == ["duplicate-screenshot"]
    assert shell_codes == ["shell-baseline-duplicate"]


def test_analyzer_contract_overrides_heuristic():
    """A flow with a contract is judged by it; heuristics must not double-flag it."""
    o = SR.FlowOutcome(
        flow="03_gui",
        is_gui=True,
        duplicate_of="00-baseline",
        has_contract=True,
        expect_failures=["screen_changed: expected True, got False"],
    )
    assert [f.code for f in SR.check_declared_expectations([o])] == ["expectation-failed"]
    assert SR.check_gui_no_effect([o]) == []
