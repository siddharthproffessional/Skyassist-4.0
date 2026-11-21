"use client";
import { useState } from "react";
import { post } from "@/lib/api";
import { Logo } from "@/components/shell/TopNav";
import { Btn, ErrorNote, SyntheticBadge } from "@/components/ui/primitives";

export default function Login() {
  const [u, setU] = useState("sarah");
  const [p, setP] = useState("coord123");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await post("/web/auth/login", { username: u, password: p, portal: "COORDINATOR" });
      const next = new URLSearchParams(window.location.search).get("next");
      window.location.href = next && next.startsWith("/") ? next : "/occ/";
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="h-full grid place-items-center p-6 bg-[radial-gradient(ellipse_at_top,#0e1a2e,transparent_60%)]">
      <form onSubmit={submit} className="glass rounded-2xl p-7 w-full max-w-sm">
        <div className="flex items-center gap-3 mb-6">
          <Logo size={30} />
          <div>
            <div className="font-semibold text-[17px] tracking-tight">SkyAssist OCC</div>
            <div className="text-[12px] text-muted">Operations controller sign-in</div>
          </div>
        </div>
        <label className="label-xs" htmlFor="u">Username</label>
        <input id="u" value={u} onChange={(e) => setU(e.target.value)} autoComplete="username"
          className="w-full mt-1 mb-3 bg-black/30 ring-1 ring-line-2 rounded-lg px-3 py-2 text-[13px] outline-none focus:ring-cyan" />
        <label className="label-xs" htmlFor="p">Password</label>
        <input id="p" type="password" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password"
          className="w-full mt-1 mb-4 bg-black/30 ring-1 ring-line-2 rounded-lg px-3 py-2 text-[13px] outline-none focus:ring-cyan" />
        <Btn type="submit" tone="primary" size="lg" className="w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in to the command centre"}</Btn>
        <div className="mt-3"><ErrorNote error={err} /></div>
        <div className="mt-5 text-[11px] text-dim leading-relaxed">
          Demonstration authentication: synthetic accounts with PBKDF2-hashed demo passwords (controllers <span className="mono">sarah</span> /
          <span className="mono"> aisha</span>). Not production identity.
        </div>
        <div className="mt-3 flex items-center justify-between">
          <SyntheticBadge />
          <a href="/passenger/login/" className="text-[12px] text-cyan hover:underline">Passenger portal →</a>
        </div>
      </form>
    </main>
  );
}
