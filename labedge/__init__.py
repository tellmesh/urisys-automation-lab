"""Compatibility shim for urisys-automation-lab edge runtime."""

from labedge.runtime import JsonlEventStore, Route, Runtime, load_json

__all__ = ["JsonlEventStore", "Route", "Runtime", "load_json"]
