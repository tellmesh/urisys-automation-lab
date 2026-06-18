from __future__ import annotations

from importlib.resources import files

from urisysedge.manifest import register_manifest_files


def manifest_paths():
    root = files(__package__)
    return [root.joinpath("manifest.yaml"), root.joinpath("manifest.tts.yaml")]


def register_manifests(runtime) -> None:
    register_manifest_files(runtime, manifest_paths())
