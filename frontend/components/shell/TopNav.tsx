"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { post } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import { SyntheticBadge } from "@/components/ui/primitives";

const NAV = [
  { href: "/occ/", label: "Live Twin" },
  { href: "/agents/", label: "Agents" },
  { href: "/recovery/", label: "Recovery" },
  { href: "/approvals/", label: "Approvals" },
  { href: "/audit/", label: "Audit" },
  { href: "/monitoring/", label: "Monitoring" },
  { href: "/demo/", label: "Demo" },
];

export function Logo({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <defs>
        <linearGradient id="lg" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stopColor="#3ec5ff" />
          <stop offset="1" stopColor="#a78bfa" />
        </linearGradient>
      </defs>
      <path d="M16 2 L29 9.5 V22.5 L16 30 L3 22.5 V9.5 Z" fill="none" stroke="url(#lg)" strokeWidth="1.6" />
      <path d="M9 18.5 L16 7.5 L23 18.5 L16 15.5 Z" fill="url(#lg)" />
      <path d="M11 22.5 H21" stroke="#3ec5ff" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export default function TopNav({ pendingApprovals }: { pendingApprovals?: number }) {
  const me = useMe();
  const [path, setPath] = useState("");
  const [clock, setClock] = useState("");
  useEffect(() => {
    setPath(window.location.pathname);
    const t = () =>
      setClock(new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Dubai" }));
    t();
    const i = setInterval(t, 15000);
    return () => clearInterval(i);
  }, []);
  return (
    <header className="h-12 shrink-0 flex items-center gap-4 px-4 border-b hairline bg-[#070c16]/90 backdrop-blur z-30 relative">
      <Link href="/occ/" className="flex items-center gap-2.5 shrink-0">
        <Logo />
        <span className="font-semibold tracking-tight text-[15px]">SkyAssist</span>
        <span className="text-[10px] mono text-dim">4.0</span>
      </Link>
      <nav className="flex items-center gap-0.5 overflow-x-auto scroll-thin" aria-label="Main">
        {NAV.map((n) => {
          const active = path.startsWith(n.href.replace(/\/$/, ""));
          return (
            <Link key={n.href} href={n.href}
              className={`relative px-3 py-1.5 rounded-md text-[12.5px] font-medium whitespace-nowrap transition-colors ${active ? "text-text bg-white/[0.06]" : "text-muted hover:text-text"}`}>
              {n.label}
              {n.label === "Approvals" && !!pendingApprovals && (
                <span className="ml-1.5 mono text-[10px] px-1.5 rounded bg-amber/20 text-amber">{pendingApprovals}</span>
              )}
              {active && <span className="absolute left-3 right-3 -bottom-[7px] h-[2px] rounded bg-cyan" />}
            </Link>
          );
        })}
      </nav>
      <div className="ml-auto flex items-center gap-3 shrink-0">
        <SyntheticBadge />
        <span className="mono text-[12px] text-muted hidden md:inline">DXB-TZ {clock}</span>
        {me.data?.signed_in && (
          <button className="text-[12px] text-muted hover:text-text" title="Sign out"
            onClick={async () => { await post("/web/auth/logout"); window.location.href = "/login/"; }}>
            {me.data.display_name} ⏻
          </button>
        )}
      </div>
    </header>
  );
}
