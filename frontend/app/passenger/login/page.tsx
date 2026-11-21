"use client";
import { useState } from "react";
import { post } from "@/lib/api";
import { Logo } from "@/components/shell/TopNav";
import { Btn, ErrorNote, SyntheticBadge } from "@/components/ui/primitives";

const DEMO = [["PNRBAG", "Rahman family — rebooked, bags separate"], ["PNR1A2", "Mehta family — wheelchair, gate change"], ["PNR0K2", "Sharma family — Hinglish, delayed"], ["OPS001", "Al Mansoori — vulnerable, SA-560"]];

export default function PassengerLogin() {
  const [u, setU] = useState("PNRBAG");
  const [p, setP] = useState("demo123");
  const [err, setErr] = useState<unknown>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await post("/web/auth/login", { username: u, password: p, portal: "PASSENGER" });
      window.location.href = "/passenger/";
    } catch (x) { setErr(x); }
  };
  return (
    <main className="min-h-full flex flex-col items-center justify-center p-5 bg-[radial-gradient(ellipse_at_top,#0e1a2e,transparent_60%)]">
      <form onSubmit={submit} className="glass rounded-2xl p-6 w-full max-w-sm">
        <div className="flex items-center gap-3 mb-5"><Logo size={28} /><div><div className="font-semibold text-[17px]">SkyAssist</div><div className="text-[12px] text-muted">Your connection, step by step</div></div></div>
        <label className="label-xs" htmlFor="b">Booking reference</label>
        <input id="b" value={u} onChange={(e) => setU(e.target.value.toUpperCase())} className="w-full mt-1 mb-3 bg-black/30 ring-1 ring-line-2 rounded-lg px-3 py-3 text-[15px] mono outline-none focus:ring-cyan" />
        <label className="label-xs" htmlFor="pw">Password</label>
        <input id="pw" type="password" value={p} onChange={(e) => setP(e.target.value)} className="w-full mt-1 mb-4 bg-black/30 ring-1 ring-line-2 rounded-lg px-3 py-3 text-[15px] outline-none focus:ring-cyan" />
        <Btn type="submit" tone="primary" size="lg" className="w-full">Continue</Btn>
        <div className="mt-3"><ErrorNote error={err} /></div>
        <div className="mt-4 label-xs">Demo bookings (synthetic, password demo123)</div>
        <div className="flex flex-col gap-1 mt-1">
          {DEMO.map(([r, d]) => <button type="button" key={r} onClick={() => setU(r)} className="text-left text-[12px] text-muted hover:text-text"><span className="mono text-cyan">{r}</span> · {d}</button>)}
        </div>
        <div className="mt-4"><SyntheticBadge /></div>
      </form>
    </main>
  );
}
