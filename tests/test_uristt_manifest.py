from __future__ import annotations

from importlib.resources import as_file

import pytest

pytest.importorskip("yaml")
from uri_control import CapabilityRegistry

import uristt


def _registry_for(index: int) -> CapabilityRegistry:
    with as_file(uristt.manifest_paths()[index]) as path:
        return CapabilityRegistry.from_manifest_files([path])


def test_stt_manifest_loads():
    registry = _registry_for(0)
    assert registry.manifests[0].scheme == "stt"
    assert len(registry.routes) == 3
    assert registry.routes[0].operation == "stt.session.start"


def test_tts_manifest_loads():
    registry = _registry_for(1)
    assert registry.manifests[0].scheme == "tts"
    assert len(registry.routes) == 1
    assert registry.routes[0].operation == "tts.session.speak"
