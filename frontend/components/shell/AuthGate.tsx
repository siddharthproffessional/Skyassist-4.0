"use client";
import { ReactNode, useEffect } from "react";
import { useMe } from "@/lib/hooks";

/** Client-side redirect to sign-in. The backend enforces the role on every call regardless. */
export default function AuthGate({ role, children }: { role: "COORDINATOR" | "PASSENGER"; children: ReactNode }) {
  const me = useMe();
  const ok = me.data?.signed_in && me.data.role === role;
  useEffect(() => {
    if (me.isSuccess && !ok) {
      const next = encodeURIComponent(window.location.pathname);
      window.location.replace(role === "PASSENGER" ? `/passenger/login/?next=${next}` : `/login/?next=${next}`);
    }
  }, [me.isSuccess, ok, role]);
  if (!ok) return <div className="h-full grid place-items-center text-dim text-sm">Checking sign-in…</div>;
  return <>{children}</>;
}
