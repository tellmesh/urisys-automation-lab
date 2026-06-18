from __future__ import annotations

from pathlib import Path
from typing import Any


def flow_expectations(flow_path: Path) -> dict[str, Any]:
    try:
        import yaml

        data = yaml.safe_load(flow_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    expect = data.get("expect") if isinstance(data, dict) else None
    return dict(expect) if isinstance(expect, dict) else {}


def ocr_texts(step_results: list[dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for step in step_results:
        result = ((step.get("response") or {}).get("result")) or {}
        stages = [result, *(s for s in (result.get("pipeline") or {}).values() if isinstance(s, dict))]
        for stage in stages:
            res = stage.get("result") if "result" in stage else stage
            if isinstance(res, dict) and isinstance(res.get("text"), str):
                texts.append(res["text"])
    return texts


def vision_confidences(step_results: list[dict[str, Any]]) -> list[float]:
    out: list[float] = []
    for step in step_results:
        result = ((step.get("response") or {}).get("result")) or {}
        stages = [result, *(s.get("result") for s in (result.get("pipeline") or {}).values() if isinstance(s, dict))]
        for res in stages:
            if isinstance(res, dict) and {"action", "confidence", "model"} <= res.keys():
                out.append(float(res.get("confidence") or 0.0))
    return out


def _screen_changed(
    expect: dict[str, Any],
    *,
    screenshot_md5: str | None,
    baseline_md5: str | None,
    duplicate_of: str | None,
) -> list[str]:
    if "screen_changed" not in expect:
        return []
    want = bool(expect["screen_changed"])
    if baseline_md5 and screenshot_md5:
        changed = screenshot_md5 != baseline_md5
    else:
        changed = duplicate_of is None
    if changed == want:
        return []
    return [
        f"screen_changed: expected {want}, got {changed} "
        f"(baseline={baseline_md5}, md5={screenshot_md5}, duplicate_of={duplicate_of})"
    ]


def _screen_changed_since_previous(
    expect: dict[str, Any],
    *,
    screenshot_md5: str | None,
    previous_md5: str | None,
    duplicate_of: str | None,
) -> list[str]:
    if "screen_changed_since_previous" not in expect:
        return []
    want = bool(expect["screen_changed_since_previous"])
    if previous_md5 and screenshot_md5:
        changed = screenshot_md5 != previous_md5
    else:
        changed = duplicate_of is None
    if changed == want:
        return []
    return [
        f"screen_changed_since_previous: expected {want}, got {changed} "
        f"(previous={previous_md5}, md5={screenshot_md5}, duplicate_of={duplicate_of})"
    ]


def _opened_url_contains(expect: dict[str, Any], step_results: list[dict[str, Any]]) -> list[str]:
    if "opened_url_contains" not in expect:
        return []
    needle = str(expect["opened_url_contains"]).lower()
    urls: list[str] = []
    for step in step_results:
        result = ((step.get("response") or {}).get("result")) or {}
        if isinstance(result.get("url"), str):
            urls.append(result["url"])
        inner = result.get("result") if isinstance(result.get("result"), dict) else {}
        if isinstance(inner, dict) and isinstance(inner.get("url"), str):
            urls.append(inner["url"])
    if any(needle in u.lower() for u in urls):
        return []
    return [f"opened_url_contains: '{expect['opened_url_contains']}' not in browser URLs {urls!r}"]


def _ocr_contains(expect: dict[str, Any], step_results: list[dict[str, Any]]) -> list[str]:
    wanted = expect.get("ocr_contains") or []
    if not wanted:
        return []
    haystack = " \n".join(ocr_texts(step_results)).lower()
    return [f"ocr_contains: '{needle}' not found in OCR output" for needle in wanted if str(needle).lower() not in haystack]


def _min_vision_confidence(expect: dict[str, Any], step_results: list[dict[str, Any]]) -> list[str]:
    if "min_vision_confidence" not in expect:
        return []
    threshold = float(expect["min_vision_confidence"])
    confidences = vision_confidences(step_results)
    best = max(confidences) if confidences else 0.0
    if best >= threshold:
        return []
    return [f"min_vision_confidence: best {best:.2f} < required {threshold:.2f}"]


def evaluate_expectations(
    expect: dict[str, Any],
    *,
    screenshot_md5: str | None = None,
    baseline_md5: str | None = None,
    previous_md5: str | None = None,
    duplicate_of: str | None = None,
    step_results: list[dict[str, Any]] | None = None,
) -> list[str]:
    if not expect:
        return []
    steps = step_results or []
    failures: list[str] = []
    failures.extend(
        _screen_changed(
            expect,
            screenshot_md5=screenshot_md5,
            baseline_md5=baseline_md5,
            duplicate_of=duplicate_of,
        )
    )
    failures.extend(
        _screen_changed_since_previous(
            expect,
            screenshot_md5=screenshot_md5,
            previous_md5=previous_md5,
            duplicate_of=duplicate_of,
        )
    )
    failures.extend(_opened_url_contains(expect, steps))
    failures.extend(_ocr_contains(expect, steps))
    failures.extend(_min_vision_confidence(expect, steps))
    return failures
