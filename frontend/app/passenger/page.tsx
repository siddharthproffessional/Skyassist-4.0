"use client";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import AuthGate from "@/components/shell/AuthGate";
import { Logo } from "@/components/shell/TopNav";
import Twin2D from "@/components/twin/Twin2D";
import { Btn, Chip, ErrorNote, SyntheticBadge } from "@/components/ui/primitives";
import { get, post } from "@/lib/api";
import { useAction, useLayout, useLiveUpdates } from "@/lib/hooks";
import { useTwin } from "@/lib/store";
import type { RouteR } from "@/lib/types";

/** Three different states, never merged: awaiting approval ≠ approved ≠ dispatched. */
function assistanceLine(a: any) {
  if (!a || !a.request) return null;
  const s = a.state as string;
  const cart = (a.request.actions_list ?? []).includes("MOBILITY_CART") || /cart/i.test(a.assigned_resource ?? "");
  if (s === "PENDING COORDINATOR APPROVAL" || s === "ESCALATED") return { tone: "amber", text: "Your request is awaiting coordinator approval." };
  if (s === "APPROVED") return { tone: "green", text: "Your request has been approved." };
  if (s === "DISPATCHED" || s === "STAFF EN ROUTE") return { tone: "green", text: cart ? "Your mobility cart has been dispatched." : "Assistance has been dispatched." };
  if (s === "DECLINED") return { tone: "red", text: "Your request was not approved." };
  if (s === "COMPLETED") return { tone: "green", text: "Assistance completed." };
  return null;
}

function Passenger() {
  useLiveUpdates();
  const q = useQuery({ queryKey: ["pax-me"], queryFn: () => get("/web/passenger/me"), refetchInterval: 10_000 });
  const layout = useLayout();
  const setFocus = useTwin((s) => s.setFocusRoute);
  const select = useTwin((s) => s.select);
  const assist = useAction("/web/passenger/assistance");
  const [dest, setDest] = useState<string>("");
  const [profile, setProfile] = useState("STANDARD");
  const [route, setRoute] = useState<RouteR | null>(null);
  const [rerr, setRerr] = useState<unknown>(null);
  const d = q.data;
  const j = d?.journey;
  useEffect(() => {
    if (j?.dest_gate && !dest) setDest(j.dest_gate);
    if (j?.needs?.some((n: string) => ["WCHR", "STROLLER", "ELDERLY"].includes(n))) setProfile("STEP_FREE");
  }, [j, dest]);
  useEffect(() => {
    if (!dest) return;
    get(`/web/passenger/route?dest=${dest}&profile=${profile}`).then((r) => { setRoute(r); setFocus(r.ok ? r.node_path : null); setRerr(null); select({ kind: "gate", id: dest }); }).catch(setRerr);
  }, [dest, profile, setFocus, select]);

  if (q.isLoading || !d) return <div className="p-6 text-dim text-sm">Loading your journey…</div>;
  const line = assistanceLine(d.assistance);
  const bag = d.baggage;
  const risk = j?.risk as string | undefined;
  const riskTone = risk === "AT_RISK" ? "red" : risk === "TIGHT" ? "amber" : "green";
  return (
    <div className="min-h-full max-w-md mx-auto px-4 pb-10">
      <header className="flex items-center justify-between py-4">
        <div className="flex items-center gap-2.5"><Logo size={24} /><span className="font-semibold">SkyAssist</span></div>
        <button className="text-[12px] text-muted" onClick={async () => { await post("/web/auth/logout"); window.location.href = "/passenger/login/"; }}>Sign out</button>
      </header>
      <div className="text-[13px] text-muted">Hello, {d.passenger}</div>
      <div className="mono text-[12px] text-dim">Booking {d.booking_ref}</div>

      <section className="glass rounded-2xl p-4 mt-3" aria-live="polite">
        <div className="label-xs">Your next flight</div>
        {j?.outbound?.found ? (
          <>
            <div className="flex items-end justify-between mt-1">
              <div>
                <div className="mono text-[26px] font-semibold leading-none">{j.outbound.flight_no}</div>
                <div className="text-[13px] text-muted mt-1">to {j.outbound.destination} · departs {j.outbound.est || j.outbound.sched}</div>
              </div>
              <div className="text-right">
                <div className="label-xs">Gate</div>
                <div className="mono text-[30px] font-semibold text-cyan leading-none">{j.outbound.gate}</div>
              </div>
            </div>
            {j.outbound.previous_gate && <div className="mt-2 text-[12.5px] text-amber">Gate changed from {j.outbound.previous_gate}.</div>}
            {j.state === "CANCELLED" && <div className="mt-2 text-[13px] text-red">{j.message}</div>}
            {j.minutes_left != null && (
              <div className="mt-3 flex items-center justify-between">
                <span className="text-[13px]">{j.minutes_left} min until boarding closes</span>
                {risk && <Chip status={risk} tone={riskTone as any} label={risk.replace("_", " ")} />}
              </div>
            )}
          </>
        ) : <div className="text-[13px] text-muted mt-1">{j?.message}</div>}
      </section>

      {d.baggage?.rebooking && (
        <section className="glass rounded-2xl p-4 mt-3">
          <div className="label-xs">Rebooking</div>
          <div className="text-[14px] mt-1">You have been rebooked from <b className="mono">{d.baggage.rebooking.from_flight}</b> to <b className="mono">{d.baggage.rebooking.to_flight}</b>, seat <b className="mono">{d.baggage.rebooking.seat_no}</b>.</div>
        </section>
      )}

      {bag && (
        <section className={`rounded-2xl p-4 mt-3 ${bag.separate ? "bg-amber/10 ring-1 ring-amber/40" : "glass"}`}>
          <div className="label-xs">Your bags</div>
          {bag.separate ? (
            <div className="text-[14px] mt-1">
              <b className="text-amber">Your bags will not arrive with you.</b> They travel on{" "}
              <b className="mono">{[...new Set(bag.assignments.map((a: any) => a.flight_no))].join(", ")}</b>
              {bag.delivery_note && <> and will be delivered: {bag.delivery_note.delivery_destination}. Expected {bag.delivery_note.expected_arrival}. Delivery note <span className="mono">{bag.delivery_note.note_id}</span>.</>}
            </div>
          ) : <div className="text-[14px] mt-1">{bag.bags.length} bag(s) {bag.assignments.length ? `booked on ${bag.assignments[0].flight_no} with you` : "in transfer"}.</div>}
        </section>
      )}

      <section className="glass rounded-2xl p-4 mt-3">
        <div className="label-xs">Assistance</div>
        {line ? <div className={`text-[15px] font-semibold mt-1 ${line.tone === "amber" ? "text-amber" : line.tone === "red" ? "text-red" : "text-green"}`}>{line.text}</div>
          : <div className="text-[13px] text-muted mt-1">No assistance requested.</div>}
        {d.assistance?.detail && <div className="text-[12px] text-muted mt-1">{d.assistance.detail}</div>}
        {!d.assistance?.request && j?.state === "OK" && (
          <div className="flex flex-wrap gap-2 mt-3">
            {[["WHEELCHAIR_AT_DOOR", "Wheelchair"], ["MOBILITY_CART", "Mobility cart"], ["STAFF_ESCORT", "Staff escort"]].map(([k, l]) => (
              <Btn key={k} onClick={() => assist.mutate({ body: { items: [k], note: "" } }, { onSuccess: () => q.refetch() })}>{l}</Btn>
            ))}
          </div>
        )}
        <ErrorNote error={assist.error} />
      </section>

      <section className="glass rounded-2xl p-4 mt-3">
        <div className="flex items-center justify-between">
          <div className="label-xs">Directions</div>
          <div className="flex gap-1">
            {["STANDARD", "STEP_FREE"].map((p) => (
              <button key={p} onClick={() => setProfile(p)} className={`text-[11px] px-2 py-1 rounded-md ring-1 ${profile === p ? "ring-cyan text-cyan" : "ring-line-2 text-muted"}`}>
                {p === "STANDARD" ? "Walking" : "Step-free"}
              </button>
            ))}
          </div>
        </div>
        <label className="text-[12px] text-muted mt-2 flex items-center gap-2">Destination gate
          <select value={dest} onChange={(e) => setDest(e.target.value)} className="bg-black/30 ring-1 ring-line-2 rounded-lg px-2 py-1.5 mono text-[13px]">
            {(layout.data?.gates ?? []).map((g) => <option key={g.gate}>{g.gate}</option>)}
          </select>
        </label>
        <div className="mt-3 h-64 rounded-xl bg-black/30 ring-1 ring-line overflow-hidden">
          {layout.data && <Twin2D layout={layout.data} compact />}
        </div>
        <ErrorNote error={rerr} />
        {route && route.ok && (
          <>
            <div className="mt-3 text-[13px]"><b className="mono">{Math.round(route.distance_m!)} m</b> · about {route.walk_min} min walking{route.profile !== "STANDARD" ? " · step-free verified" : ""}</div>
            <ol className="mt-2 flex flex-col gap-1.5">
              {route.steps!.map((s, i) => <li key={i} className="text-[13px] flex gap-2"><span className="mono text-cyan">{i + 1}</span>{s}</li>)}
            </ol>
          </>
        )}
        {route && !route.ok && <div className="mt-3 text-[13px] text-red">{route.reason}</div>}
      </section>

      {j?.messages?.length > 0 && (
        <section className="glass rounded-2xl p-4 mt-3">
          <div className="label-xs">SkyAssist guidance</div>
          {j.messages.map((m: string, i: number) => <p key={i} className="text-[13px] mt-1.5">{m}</p>)}
        </section>
      )}
      {d.notifications?.length > 0 && (
        <section className="glass rounded-2xl p-4 mt-3">
          <div className="label-xs">Notifications</div>
          {d.notifications.slice(0, 6).map((n: any) => <p key={n.id} className="text-[12.5px] mt-1.5 text-muted">{n.message}</p>)}
        </section>
      )}
      <div className="mt-4 flex justify-center"><SyntheticBadge /></div>
    </div>
  );
}

export default function Page() {
  return <AuthGate role="PASSENGER"><Passenger /></AuthGate>;
}
