"""SkyAssist 4.0 — DIGITAL TWIN GEOMETRY SOURCES (extension point for NVIDIA Omniverse / OpenUSD).

The browser twin consumes one contract, whatever produced the geometry:
    {"source": str, "status": str, "glb_url": str | None, "topology": "routing-graph", "notes": str}
Operational state NEVER comes from a geometry source — it always comes from the SkyAssist database via
services/twin/state.py. A geometry source only supplies shapes and (later) surveyed coordinates.

Implemented now
  * ProceduralGraphSource — the browser builds the terminal procedurally from the routing graph (default).
  * ApprovedGLBSource     — an approved, licensed GLB file served from frontend/public (SKYASSIST_TWIN_GLB).
Prepared, NOT connected
  * OpenUSDSource         — interface for USD stage geometry, gate coordinates, terminal topology, dynamic
                            obstacles and resource locations from Omniverse. No live Omniverse connection exists;
                            describe() says so and nothing calls it on a request path.
"""
import os
from typing import Protocol


class TwinGeometrySource(Protocol):
    name: str

    def describe(self) -> dict: ...


class ProceduralGraphSource:
    name = "procedural-graph"

    def describe(self):
        return {"source": self.name, "status": "ACTIVE", "glb_url": None, "topology": "routing-graph",
                "notes": "Procedural terminal derived from terminal_nodes/terminal_edges (illustrative geometry)."}


class ApprovedGLBSource:
    name = "approved-glb"

    def __init__(self, url):
        self.url = url

    def describe(self):
        return {"source": self.name, "status": "ACTIVE", "glb_url": self.url, "topology": "routing-graph",
                "notes": "Approved GLB rendered for the terminal shell; gates, stands and routes still come from the "
                         "routing graph."}


class OpenUSDSource:
    """Future adapter. Expected inputs: a USD stage (e.g. omniverse://…/airport.usd) exposing prims for terminal
    geometry, /Gates/<id> xforms, topology relationships, dynamic obstacles, passenger/baggage movement samples and
    resource locations. Output: the same describe() contract plus surveyed node coordinates."""
    name = "openusd"

    def __init__(self, stage_url):
        self.stage_url = stage_url

    def describe(self):
        return {"source": self.name, "status": "NOT_CONNECTED", "glb_url": None, "topology": "routing-graph",
                "notes": f"OpenUSD/Omniverse adapter prepared for {self.stage_url!r} but not implemented or tested — "
                         "no live Omniverse connection exists."}

    def load_gate_coordinates(self):  # pragma: no cover - deliberately not implemented
        raise NotImplementedError("Omniverse/OpenUSD integration is a future extension (see docs/v4/ARCHITECTURE.md).")


def active_source() -> TwinGeometrySource:
    if os.getenv("SKYASSIST_TWIN_USD"):
        return OpenUSDSource(os.environ["SKYASSIST_TWIN_USD"])
    glb = os.getenv("SKYASSIST_TWIN_GLB")
    if glb:
        return ApprovedGLBSource(glb)
    return ProceduralGraphSource()
