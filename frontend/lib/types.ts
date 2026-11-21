export type GateStatus =
  | "AVAILABLE" | "OCCUPIED" | "BOARDING" | "DEPARTING" | "BLOCKED" | "UNDER_REVIEW" | "PENDING_APPROVAL";

export interface TNode { node_id: string; name: string; node_type: string; concourse: string; floor: number; x: number; y: number }
export interface TEdge {
  edge_id: string; from_node: string; to_node: string; distance_m: number; accessible: number; stairs: number;
  escalator: number; elevator: number; cart_ok: number; kind: string; direction_description: string;
  geometry: number[][] | null; available: number; closure_reason: string | null;
}
export interface Layout { nodes: TNode[]; edges: TEdge[]; gates: { gate: string; concourse: string; number: number }[]; label: string }

export interface Flight {
  flight_no: string; origin: string; destination: string; direction: "ARRIVAL" | "DEPARTURE"; status: string;
  gate: string | null; previous_gate: string | null; sched: string; est: string | null; boarding_close: string | null;
  aircraft_reg?: string | null; health: "normal" | "warning" | "critical"; reasons: string[];
  holds: { type: string; reason: string }[]; passengers: number;
}
export interface Gate {
  gate: string; concourse: string; number: number; status: GateStatus; departures: string[]; arrivals: string[];
  cancelled: string[]; pending_approvals: any[]; stale_approvals: any[]; version: number;
  gate_changed_away: string[]; affected: boolean;
}
export interface Agent {
  agent_id: string; name: string; short: string; color: string; responsibility: string; tools: string[];
  never: string[]; status: string; label: string; last: string; last_tool: string | null; last_at: string | null;
  mission_id: string | null; steps: number;
}
export interface Kpis {
  active_flights: number; disrupted_flights: number; affected_passengers: number; pending_approvals: number;
  pending_breakdown: Record<string, number>; rebooked_passengers: number; successful_recoveries: number;
  failed_transactions: number; open_alerts: number; closed_corridors: number;
}
export interface TwinState {
  version: string; label: string; epoch: number; flights: Flight[]; gates: Gate[];
  closed_edges: { edge_id: string; from_node: string; to_node: string; closure_reason: string }[];
  kpis: Kpis; alerts: any[]; agents: Agent[]; events: any[];
  health: { providers: { provider: string; status: string; last_outcome: string | null }[]; rules_fallback: string;
    n8n_mode: string; outbox: Record<string, number> };
}
export interface RouteR {
  from: string; to: string; profile: string; ok: boolean; distance_m?: number; node_path?: string[];
  edge_path?: string[]; walk_min?: number; steps?: string[]; bookings?: string[]; needs?: string[]; reason?: string;
}
export interface BagLeg {
  from_gate: string | null; to_gate: string | null; kind: string; bag_flight: string; passenger_flight: string;
  bags: string[]; discrepancy: boolean;
}
export interface MissionStep {
  step_id: number; seq: number; agent_id: string; agent_name: string; tool: string | null; phase: string;
  status: string; args: string; result_summary: string; latency_ms: number | null; source: string; created_at: string;
}
export interface Mission {
  mission_id: string; kind: string; title: string; status: string; summary: string; created_at: string;
  finished_at: string; steps: MissionStep[]; step_count?: number;
}
export interface ApprovalItem {
  kind: "gate" | "journey" | "crew" | "batch" | "assistance"; id: string; status: string; flight: string | null;
  policy: string; title: string; recommendation: string; why: string; validations_passed: string[];
  validations_failed: string[]; state_change: string; risks: string; if_declined: string; expires_at: string | null;
  state_version: any; snapshot_hash: string | null; can_execute: boolean; requested_at: string | null;
  decided_by: string | null; parent_id?: string | null; superseded_by?: string | null;
}
