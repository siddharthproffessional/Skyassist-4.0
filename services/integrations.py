"""FUTURE-READY INTEGRATION INTERFACES — nothing here pretends to be connected.

Each external capability sits behind an interface. Only the SYNTHETIC SQLite implementations are wired up.
Every other provider raises NotConfigured, so the UI can say honestly that a source is unavailable.

Data provenance labels used across the app:
  SYNTHETIC  demonstration data generated for this MVP (everything today)
  CONFIGURED an external source has been configured but its data is not verified live
  LIVE       verified live data from an airport/airline system (none yet)
"""
from abc import ABC, abstractmethod

from db import query, query_one

SYNTHETIC, CONFIGURED, LIVE = "SYNTHETIC", "CONFIGURED", "LIVE"


class NotConfigured(Exception):
    pass


# ---------------------------------------------------------------- flight data
class FlightDataProvider(ABC):
    source = SYNTHETIC

    @abstractmethod
    def get_flight(self, flight_no: str):
        ...


class SQLiteFlightProvider(FlightDataProvider):
    source = SYNTHETIC

    def get_flight(self, flight_no):
        return query_one("SELECT * FROM flights WHERE flight_no=?", (flight_no.upper(),))


class LiveFlightProvider(FlightDataProvider):
    """e.g. airport AODB / airline API / OpenSky. Not configured in this MVP."""
    source = LIVE

    def get_flight(self, flight_no):
        raise NotConfigured("No live flight data provider is configured.")


# ---------------------------------------------------------------- terminal topology (incl. SkyOps Twin)
class TerminalTopologyProvider(ABC):
    source = SYNTHETIC

    @abstractmethod
    def nodes(self):
        ...

    @abstractmethod
    def edges(self):
        ...


class SQLiteTopologyProvider(TerminalTopologyProvider):
    def nodes(self):
        return query("SELECT * FROM terminal_nodes")

    def edges(self):
        return query("SELECT * FROM terminal_edges")


class SkyOpsTwinTopologyProvider(TerminalTopologyProvider):
    """Future: the SkyOps Twin digital twin supplies gate positions, corridor availability, blocked routes,
    lift status and dynamic conditions in the same node/edge shape, so routing_engine.RoutingEngine(nodes, edges)
    can consume it without changing the passenger or coordinator apps. Deliberately NOT implemented."""
    source = CONFIGURED

    def nodes(self):
        raise NotConfigured("SkyOps Twin integration is not connected.")

    def edges(self):
        raise NotConfigured("SkyOps Twin integration is not connected.")


# ---------------------------------------------------------------- operations
class DispatchProvider(ABC):
    """Mobility-cart / staff dispatch system. Today the coordinator records dispatch manually."""

    @abstractmethod
    def dispatch(self, request_id, staff_id, resource_id):
        ...


class ManualDispatchProvider(DispatchProvider):
    def dispatch(self, request_id, staff_id, resource_id):
        return {"mode": "MANUAL", "note": "Recorded by coordinator; no external dispatch system connected."}


class NotificationChannel(ABC):
    """Airport notification systems (SMS, app push, PA). Today: in-app notification feed only."""

    @abstractmethod
    def send(self, booking_ref, message):
        ...


class InAppNotificationChannel(NotificationChannel):
    def send(self, booking_ref, message):
        return {"channel": "IN_APP"}
