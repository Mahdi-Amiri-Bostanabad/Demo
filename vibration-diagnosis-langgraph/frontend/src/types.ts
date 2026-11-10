export type Json = any;

export interface Asset {
  id: string; name: string; type: string; site: string; rpm: number; power_kw: number;
  iso_group: string; foundation: string; coupling: string; criticality: string;
  bearing: { model: string; n_balls: number; ball_d_mm: number; pitch_d_mm: number; contact_deg: number };
  measurement_points: string[];
}
export interface Scenario { id: string; label: string; fault: string; blurb: string }
export interface LlmStatus { available: boolean | null; detail: string; model: string }
export interface Meta {
  assets: Asset[]; scenarios: Scenario[]; levels: string[]; agents: Record<string, string>; llm: LlmStatus;
}
export interface Topology {
  nodes: { id: string; label: string }[];
  edges: { source: string; target: string; conditional: boolean }[];
  mermaid: string;
}

export interface Ev {
  seq: number; kind: string; ts: string;
  [k: string]: Json;
}

export interface Checkpoint {
  checkpoint_id: string; step: number; next: string[]; values: Record<string, Json>; source: string; seq: number;
}

export type NodeStatus = "idle" | "active" | "done" | "interrupted" | "error";

export interface FeedItem {
  seq: number; ts: string; agent: string; kind: string; text: string; live?: boolean;
}

export interface RunView {
  threadId: string | null;
  status: "idle" | "running" | "interrupted" | "done" | "error";
  error?: string;
  doneAt?: string;
  meta?: Json;
  checkpoints: Checkpoint[];
  stepTasks: Record<number, string[]>;
  nodeStatus: Record<string, NodeStatus>;
  visits: Record<string, number>;
  edgeCounts: Record<string, number>;
  lastEdges: string[];
  values: Record<string, Json>;
  lastWriter: Record<string, { node: string; step: number }>;
  interrupt: Json | null;
  progress: Record<string, string>;
  tokens: Record<string, string>;
  feed: FeedItem[];
  curStep: number;
}

export interface SignalPreview {
  waveform: { t_ms: number[]; g: number[] };
  spectrum: { f: number[]; v: number[]; unit: string };
  envelope: { f: number[]; a: number[]; unit: string };
}
