"""ASYNC HUMAN-APPROVAL CALLBACK ENGINE (v2: durable).

* SQLite (services/request_store.py) is the source of truth for every request and decision.
* Live agent waits use an asyncio.Future on a dedicated event-loop thread, so the UI never blocks and
  the loop stays free while any number of requests are pending.
* A coordinator decision first commits atomically in SQLite, THEN wakes the waiting Future.
  If the app restarted and no Future exists, the decision is still stored and visible to the passenger.
* A timeout only escalates. It is never treated as approval.
"""
import asyncio
import threading
import time

from services import request_store


class ApprovalEngine:
    def __init__(self, interim_after_s: float = request_store.ESCALATE_AFTER_S):
        self.interim_after_s = interim_after_s
        self.loop = asyncio.new_event_loop()
        self._futures = {}
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, daemon=True, name="approval-loop")
        self._thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _new_future(self):
        return self.loop.create_future()

    def _future_for(self, req_id):
        with self._lock:
            fut = self._futures.get(req_id)
            if fut is None:
                if threading.current_thread() is self._thread:
                    fut = self.loop.create_future()
                else:
                    fut = asyncio.run_coroutine_threadsafe(self._new_future(), self.loop).result()
                self._futures[req_id] = fut
            return fut

    # ---- requests
    def stage_ex(self, conv_id, booking_ref, actions, reason, context, source="AGENT"):
        """Durably create (or reuse) a request and prepare a Future. Returns (req_id, created)."""
        req_id, created = request_store.create_request(conv_id, booking_ref, actions, reason, context, source)
        self._future_for(req_id)
        return req_id, created

    def stage(self, conv_id, booking_ref, actions, reason, context) -> str:
        return self.stage_ex(conv_id, booking_ref, actions, reason, context)[0]

    def run_continuation(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    async def wait(self, req_id, on_interim=None) -> dict:
        """Suspend until a human decides. If the request was already decided (e.g. after a restart),
        return the durable decision immediately."""
        stored = request_store.get(req_id)
        if stored and stored["status"] != "PENDING":
            return self._decision(stored)
        fut = self._future_for(req_id)
        while True:
            try:
                return await asyncio.wait_for(asyncio.shield(fut), timeout=self.interim_after_s)
            except asyncio.TimeoutError:
                await asyncio.to_thread(request_store.escalate_if_overdue, req_id, 0)
                if on_interim:
                    await asyncio.to_thread(on_interim, req_id)

    @staticmethod
    def _decision(r):
        return {"request_id": r["id"], "status": r["status"], "staff": r["resolved_by"], "note": r["note"] or "",
                "hold_minutes": r.get("hold_minutes_approved") or 0}

    def notify_decided(self, req_id):
        """Wake the waiting agent (if any) with the decision already committed in SQLite."""
        stored = request_store.get(req_id)
        with self._lock:
            fut = self._futures.pop(req_id, None)
        if fut is not None and stored and stored["status"] != "PENDING":
            decision = self._decision(stored)
            self.loop.call_soon_threadsafe(lambda: fut.done() or fut.set_result(decision))
            return True
        return False

    # ---- backwards-compatible single call used by run_scenarios.py
    def resolve(self, req_id, approved: bool, staff: str, note: str = "", hold_minutes=None) -> bool:
        try:
            request_store.decide(req_id, approved, staff, note, hold_minutes)
        except request_store.StateConflict:
            return False
        self.notify_decided(req_id)
        return True

    def has_waiter(self, req_id) -> bool:
        with self._lock:
            return req_id in self._futures

    def ping_ms(self) -> float:
        async def _p():
            return time.perf_counter()
        t0 = time.perf_counter()
        asyncio.run_coroutine_threadsafe(_p(), self.loop).result(timeout=2)
        return (time.perf_counter() - t0) * 1000


async def request_mobility_dispatch_async(engine: ApprovalEngine, conv_id, booking_ref, actions, reason,
                                          context, on_staged=None, on_interim=None) -> dict:
    """TOOL 3. Stages a physical-assistance request and suspends until a human decides."""
    req_id = engine.stage(conv_id, booking_ref, actions, reason, context)
    if on_staged:
        on_staged(req_id)
    return await engine.wait(req_id, on_interim)


# ---- process-wide singleton shared by all Streamlit sessions and services
_ENGINE = None
_ENGINE_LOCK = threading.Lock()


def get_engine() -> ApprovalEngine:
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = ApprovalEngine()
        return _ENGINE
