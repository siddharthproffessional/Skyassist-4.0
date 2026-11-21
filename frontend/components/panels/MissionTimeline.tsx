"use client";
import { motion, AnimatePresence } from "framer-motion";
import { useEffect, useState } from "react";
import type { Mission } from "@/lib/types";
import { Chip } from "@/components/ui/primitives";
import { localTime } from "@/lib/format";
import { statusTone, TONE_HEX } from "@/lib/colors";

const AGENT_COLOR: Record<string, string> = {
  flight_intel: "#a78bfa", passenger_recovery: "#3ec5ff", crew_compliance: "#f5b544", maintenance: "#f25f5c",
  baggage: "#f5b544", gate_resource: "#3ec5ff", communication: "#e9eef6", safety_supervisor: "#34d399",
};

/** Recorded execution timeline. `reveal` replays the recorded steps one by one (presentation only). */
export default function MissionTimeline({ mission, reveal = false, compact = false }: { mission?: Mission; reveal?: boolean; compact?: boolean }) {
  const steps = mission?.steps ?? [];
  const [n, setN] = useState(reveal ? 0 : steps.length);
  useEffect(() => {
    if (!reveal) { setN(steps.length); return; }
    setN(0);
    let i = 0;
    const t = setInterval(() => {
      i += 1;
      setN(i);
      if (i >= steps.length) clearInterval(t);
    }, 260);
    return () => clearInterval(t);
  }, [mission?.mission_id, steps.length, reveal]);
  if (!mission) return null;
  return (
    <div>
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="min-w-0">
          <div className="text-[12.5px] font-semibold leading-snug">{mission.title}</div>
          <div className="text-[10.5px] text-dim mono">{mission.mission_id} · {localTime(mission.created_at, true)} · recorded execution</div>
        </div>
        <Chip status={mission.status} />
      </div>
      <ol className="relative ml-1.5">
        <span className="absolute left-[5px] top-1 bottom-1 w-px bg-line-2" aria-hidden />
        <AnimatePresence initial={false}>
          {steps.slice(0, n).map((s) => {
            const tone = statusTone(s.status);
            return (
              <motion.li key={s.step_id} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.22 }}
                className="relative pl-5 pb-2.5">
                <span className="absolute left-0 top-[5px] w-[11px] h-[11px] rounded-full ring-2 ring-[#0b1220]"
                  style={{ background: TONE_HEX[tone] }} aria-hidden />
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-[10.5px] font-semibold tracking-wide" style={{ color: AGENT_COLOR[s.agent_id] ?? "#93a1b5" }}>
                    {s.agent_name}
                  </span>
                  {s.tool && <span className="mono text-[10px] text-muted bg-white/5 rounded px-1">{s.tool}()</span>}
                  {!s.tool && <span className="mono text-[10px] text-dim">{s.source}</span>}
                  <Chip status={s.status} size="xs" />
                  {s.latency_ms != null && !compact && <span className="mono text-[10px] text-dim">{Math.round(s.latency_ms)} ms</span>}
                </div>
                <div className={`text-[11.5px] text-muted leading-snug mt-0.5 ${compact ? "line-clamp-2" : ""}`}>{s.result_summary}</div>
              </motion.li>
            );
          })}
        </AnimatePresence>
      </ol>
      {mission.summary && n >= steps.length && (
        <div className="text-[11.5px] mt-1 px-2.5 py-2 rounded-lg bg-white/[0.03] ring-1 ring-line">{mission.summary}</div>
      )}
    </div>
  );
}
