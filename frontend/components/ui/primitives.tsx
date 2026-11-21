"use client";
import { ReactNode } from "react";
import { statusTone, TONE_HEX } from "@/lib/colors";

export function Panel({ title, right, children, className = "", bodyClass = "" }: {
  title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; bodyClass?: string;
}) {
  return (
    <section className={`glass rounded-xl overflow-hidden flex flex-col ${className}`}>
      {title !== undefined && (
        <header className="flex items-center justify-between px-3.5 pt-3 pb-2">
          <h2 className="label-xs">{title}</h2>
          {right}
        </header>
      )}
      <div className={`min-h-0 ${bodyClass}`}>{children}</div>
    </section>
  );
}

const ICON: Record<string, string> = { green: "✓", amber: "◷", red: "■", cyan: "●", violet: "◆", slate: "○" };

/** Status chip: colour + glyph + text, never colour alone. */
export function Chip({ status, label, tone, size = "sm" }: {
  status?: string | null; label?: ReactNode; tone?: keyof typeof TONE_HEX; size?: "xs" | "sm";
}) {
  const t = tone ?? statusTone(status);
  const hex = TONE_HEX[t];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md font-semibold whitespace-nowrap mono ${size === "xs" ? "text-[9.5px] px-1.5 py-[1px]" : "text-[10.5px] px-2 py-0.5"}`}
      style={{ color: hex, background: `${hex}1a`, boxShadow: `inset 0 0 0 1px ${hex}33` }}
    >
      <span aria-hidden>{ICON[t]}</span>
      {label ?? (status ?? "").replace(/_/g, " ")}
    </span>
  );
}

export function Btn({ children, onClick, tone = "default", disabled, className = "", title, size = "md", type = "button" }: {
  children: ReactNode; onClick?: () => void; tone?: "default" | "primary" | "approve" | "decline" | "ghost" | "violet";
  disabled?: boolean; className?: string; title?: string; size?: "sm" | "md" | "lg"; type?: "button" | "submit";
}) {
  const tones: Record<string, string> = {
    default: "bg-surface-2 hover:bg-[#18243a] text-text ring-1 ring-line-2",
    primary: "bg-cyan/15 hover:bg-cyan/25 text-cyan ring-1 ring-cyan/40",
    approve: "bg-green/15 hover:bg-green/25 text-green ring-1 ring-green/45",
    decline: "bg-red/10 hover:bg-red/20 text-red ring-1 ring-red/40",
    violet: "bg-violet/15 hover:bg-violet/25 text-violet ring-1 ring-violet/40",
    ghost: "hover:bg-white/5 text-muted",
  };
  const sizes = { sm: "text-[11px] px-2 py-1", md: "text-[12px] px-3 py-1.5", lg: "text-[13px] px-4 py-2.5" };
  return (
    <button type={type} title={title} onClick={onClick} disabled={disabled}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg font-semibold tracking-wide transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${tones[tone]} ${sizes[size]} ${className}`}>
      {children}
    </button>
  );
}

export function Metric({ label, value, tone, sub }: { label: string; value: ReactNode; tone?: keyof typeof TONE_HEX; sub?: ReactNode }) {
  return (
    <div className="flex flex-col min-w-0">
      <span className="label-xs truncate">{label}</span>
      <span className="text-[19px] font-semibold leading-tight mono" style={tone ? { color: TONE_HEX[tone] } : undefined}>
        {value}
      </span>
      {sub && <span className="text-[10.5px] text-dim truncate">{sub}</span>}
    </div>
  );
}

export function SyntheticBadge({ text = "Synthetic demo data" }: { text?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[10px] font-semibold tracking-wider uppercase text-amber bg-amber/10 ring-1 ring-amber/30">
      <span aria-hidden>◬</span>{text}
    </span>
  );
}

export function KV({ k, v, mono = false }: { k: string; v: ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-[3px] text-[12px]">
      <span className="text-dim shrink-0">{k}</span>
      <span className={`text-right truncate ${mono ? "mono" : ""}`}>{v ?? "—"}</span>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="text-[12px] text-dim px-3.5 py-3">{children}</div>;
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  return <div role="alert" className="text-[12px] text-red bg-red/10 ring-1 ring-red/30 rounded-lg px-3 py-2">{msg}</div>;
}
