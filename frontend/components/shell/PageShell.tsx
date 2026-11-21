"use client";
import { ReactNode } from "react";
import AuthGate from "./AuthGate";
import TopNav from "./TopNav";
import StatusBar from "./StatusBar";
import { useLiveUpdates, useTwinState } from "@/lib/hooks";

function Inner({ title, subtitle, actions, children, full = false }: { title: string; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; full?: boolean }) {
  const live = useLiveUpdates();
  const st = useTwinState();
  return (
    <div className="h-full flex flex-col">
      <TopNav pendingApprovals={st.data?.kpis.pending_approvals} />
      <main className={`flex-1 min-h-0 ${full ? "flex flex-col overflow-y-auto scroll-thin xl:overflow-hidden" : "overflow-y-auto scroll-thin"}`}>
        <div className={`${full ? "flex-1 min-h-0 flex flex-col" : ""} px-5 py-4 max-w-[1680px] w-full mx-auto`}>
          <div className="flex items-end justify-between gap-4 mb-4 shrink-0">
            <div>
              <h1 className="text-[20px] font-semibold tracking-tight">{title}</h1>
              {subtitle && <p className="text-[12.5px] text-muted mt-0.5 max-w-3xl">{subtitle}</p>}
            </div>
            <div className="flex items-center gap-2 shrink-0">{actions}</div>
          </div>
          {children}
        </div>
      </main>
      <StatusBar s={st.data} live={live} />
    </div>
  );
}

export default function PageShell(props: { title: string; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; full?: boolean }) {
  return <AuthGate role="COORDINATOR"><Inner {...props} /></AuthGate>;
}
