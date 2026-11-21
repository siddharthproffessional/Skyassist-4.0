"""LOCATION PROVIDERS — replaceable interface for where the passenger is starting from.

The MVP has NO live positioning. ManualLocationProvider uses the known arrival gate, or a location the
passenger chose by hand. Future providers (device location, BLE beacons, QR checkpoints, UWB) implement the
same interface and must set `live=True` only when a genuine positioning fix exists.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from db import query_one, tx, utcnow
from services.integrations import NotConfigured


@dataclass
class LocationFix:
    node_id: str
    label: str
    source: str        # "ARRIVAL_GATE" | "MANUAL" | future: "BLE" | "QR" | "UWB" | "DEVICE"
    live: bool = False  # True only for a genuine real-time positioning fix


class LocationProvider(ABC):
    @abstractmethod
    def current(self, booking_ref: str, arrival_gate: str) -> LocationFix:
        ...


class ManualLocationProvider(LocationProvider):
    def current(self, booking_ref, arrival_gate):
        row = query_one("SELECT origin_override, location_source FROM route_progress WHERE booking_ref=?",
                        (booking_ref,))
        if row and row["origin_override"]:
            node = query_one("SELECT name FROM terminal_nodes WHERE node_id=?", (row["origin_override"],))
            return LocationFix(row["origin_override"], node["name"] if node else row["origin_override"], "MANUAL")
        return LocationFix(f"G_{arrival_gate}", f"Gate {arrival_gate} (your arrival gate)", "ARRIVAL_GATE")

    @staticmethod
    def set_manual(booking_ref, node_id):
        with tx() as con:
            con.execute("INSERT INTO route_progress(booking_ref, origin_override, location_source, step_index, "
                        "started, updated_at) VALUES(?,?, 'MANUAL', 0, 0, ?) ON CONFLICT(booking_ref) DO UPDATE SET "
                        "origin_override=excluded.origin_override, location_source='MANUAL', step_index=0, "
                        "updated_at=excluded.updated_at", (booking_ref, node_id, utcnow()))

    @staticmethod
    def clear_manual(booking_ref):
        with tx() as con:
            con.execute("UPDATE route_progress SET origin_override=NULL, location_source=NULL, step_index=0, "
                        "updated_at=? WHERE booking_ref=?", (utcnow(), booking_ref))


class BeaconLocationProvider(LocationProvider):
    def current(self, booking_ref, arrival_gate):
        raise NotConfigured("BLE beacon positioning is not connected.")


class QRCheckpointLocationProvider(LocationProvider):
    def current(self, booking_ref, arrival_gate):
        raise NotConfigured("QR checkpoint scanning is not connected.")


def get_location_provider() -> LocationProvider:
    return ManualLocationProvider()
