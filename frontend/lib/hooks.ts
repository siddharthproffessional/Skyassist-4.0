"use client";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { get, post } from "./api";
import type { ApprovalItem, BagLeg, Layout, Mission, RouteR, TwinState, Agent } from "./types";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => get("/web/auth/me"), staleTime: 30_000 });
}

/** Server-sent events: the backend emits a new state version after any audited change; we refetch. */
export function useLiveUpdates(enabled = true) {
  const qc = useQueryClient();
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    if (!enabled || typeof EventSource === "undefined") return;
    let es: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let last = "";
    const open = () => {
      es = new EventSource("/web/events");
      es.addEventListener("open", () => setConnected(true));
      es.addEventListener("state", (ev) => {
        try {
          const v = JSON.parse((ev as MessageEvent).data).version;
          if (last && v !== last) qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "layout" && q.queryKey[0] !== "me" });
          last = v;
        } catch {}
      });
      es.onerror = () => {
        setConnected(false);
        es?.close();
        retry = setTimeout(open, 3000);
      };
    };
    open();
    return () => {
      es?.close();
      if (retry) clearTimeout(retry);
    };
  }, [enabled, qc]);
  return connected;
}

export const useLayout = () =>
  useQuery<Layout>({ queryKey: ["layout"], queryFn: () => get("/web/twin/layout"), staleTime: Infinity });

export const useTwinState = () =>
  useQuery<TwinState>({ queryKey: ["state"], queryFn: () => get("/web/twin/state"), refetchInterval: 20_000 });

export const useFlight = (no?: string | null) =>
  useQuery({ queryKey: ["flight", no], queryFn: () => get(`/web/flights/${no}`), enabled: !!no });

export const useGate = (g?: string | null) =>
  useQuery({ queryKey: ["gate", g], queryFn: () => get(`/web/gates/${g}`), enabled: !!g });

export const useRoutes = (flight?: string | null) =>
  useQuery<{ routes: RouteR[] }>({
    queryKey: ["routes", flight ?? "all"],
    queryFn: () => get(`/web/routes/connections${flight ? `?flight=${flight}` : ""}`),
  });

export const useBagLegs = (flight?: string | null) =>
  useQuery<{ legs: BagLeg[] }>({
    queryKey: ["bags", flight ?? "all"],
    queryFn: () => get(`/web/routes/baggage${flight ? `?flight=${flight}` : ""}`),
  });

export const useAgents = () =>
  useQuery<{ agents: Agent[]; tools: Record<string, { kind: string; description: string }>; human_only: Record<string, string> }>({
    queryKey: ["agents"], queryFn: () => get("/web/agents"),
  });

export const useMissions = (limit = 12) =>
  useQuery<{ missions: Mission[] }>({ queryKey: ["missions", limit], queryFn: () => get(`/web/missions?limit=${limit}`) });

export const useMission = (id?: string | null) =>
  useQuery<Mission>({ queryKey: ["mission", id], queryFn: () => get(`/web/missions/${id}`), enabled: !!id });

export const useApprovals = () =>
  useQuery<{ items: ApprovalItem[]; pending: number }>({ queryKey: ["approvals"], queryFn: () => get("/web/approvals") });

export const useScenarios = () =>
  useQuery<{ scenarios: any[]; metrics: Record<string, any> }>({ queryKey: ["scenarios"], queryFn: () => get("/web/scenarios") });

/** POST helper that refreshes every live query afterwards. */
export function useAction<T = any>(path: string | ((v: any) => string)) {
  const qc = useQueryClient();
  return useMutation<T, Error, any>({
    mutationFn: (vars: any) => post<T>(typeof path === "function" ? path(vars) : path, vars?.body ?? vars ?? {}),
    onSettled: () => qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "layout" && q.queryKey[0] !== "me" }),
  });
}
