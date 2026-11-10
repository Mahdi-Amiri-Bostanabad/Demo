export type NodeKind = "terminal" | "dsp" | "supervisor" | "llm" | "tool" | "human" | "output";

export const NODE_META: Record<string, { kind: NodeKind; label: string; sub: string; x: number; y: number }> = {
  __start__: { kind: "terminal", label: "START", sub: "route request", x: 0, y: 22 },
  acquisition: { kind: "dsp", label: "Data Acquisition", sub: "wireless accelerometer", x: 100, y: 0 },
  signal_qa: { kind: "dsp", label: "Signal Quality", sub: "clipping · ski slope · rattle", x: 290, y: 0 },
  severity: { kind: "dsp", label: "ISO 20816 Severity", sub: "velocity RMS → zone", x: 480, y: -85 },
  spectral: { kind: "dsp", label: "Spectral Analysis", sub: "FFT · orders · envelope", x: 480, y: 85 },
  triage: { kind: "supervisor", label: "Supervisor · Triage", sub: "healthy fast path?", x: 670, y: 0 },
  diagnostician: { kind: "llm", label: "Diagnostician", sub: "LLM + tool calling", x: 860, y: 0 },
  diag_tools: { kind: "tool", label: "Engineering Toolbox", sub: "ToolNode · 7 tools", x: 860, y: -165 },
  confidence_gate: { kind: "supervisor", label: "Supervisor · Confidence", sub: "need more data?", x: 1050, y: 0 },
  prognosis: { kind: "dsp", label: "Prognosis / RUL", sub: "trend fit → life", x: 1050, y: 270 },
  planner: { kind: "llm", label: "Maintenance Planner", sub: "LLM + policy guardrail", x: 860, y: 270 },
  human_review: { kind: "human", label: "Engineer Approval", sub: "interrupt() · HITL", x: 670, y: 270 },
  report: { kind: "output", label: "Report", sub: "close-out", x: 290, y: 270 },
  __end__: { kind: "terminal", label: "END", sub: "", x: 110, y: 292 },
};

export const KIND_STYLE: Record<NodeKind, { color: string; tag: string }> = {
  terminal: { color: "#737373", tag: "" },
  dsp: { color: "#22d3ee", tag: "DSP agent" },
  supervisor: { color: "#d4d4d8", tag: "Router" },
  llm: { color: "#f472b6", tag: "LLM agent" },
  tool: { color: "#fbbf24", tag: "Tools" },
  human: { color: "#fb923c", tag: "Human" },
  output: { color: "#34d399", tag: "Output" },
};

// [sourceHandle, targetHandle] overrides so loops and back-edges read clearly
export const EDGE_HANDLES: Record<string, [string, string]> = {
  "__start__->acquisition": ["r", "l"],
  "acquisition->signal_qa": ["r", "l"],
  "signal_qa->acquisition": ["t", "t"],
  "signal_qa->severity": ["r", "l"],
  "signal_qa->spectral": ["r", "l"],
  "signal_qa->report": ["b", "t"],
  "severity->triage": ["r", "l"],
  "spectral->triage": ["r", "l"],
  "triage->diagnostician": ["r", "l"],
  "triage->report": ["b", "r"],
  "diagnostician->diag_tools": ["t", "b"],
  "diag_tools->diagnostician": ["r", "r"],
  "diagnostician->confidence_gate": ["r", "l"],
  "confidence_gate->acquisition": ["t", "t"],
  "confidence_gate->prognosis": ["b", "t"],
  "confidence_gate->report": ["b", "r"],
  "prognosis->planner": ["l", "r"],
  "planner->human_review": ["l", "r"],
  "planner->report": ["b", "b"],
  "human_review->planner": ["b", "b"],
  "human_review->report": ["l", "r"],
  "report->__end__": ["l", "r"],
};

export const EDGE_LABELS: Record<string, string> = {
  "signal_qa->acquisition": "reject → re-acquire",
  "signal_qa->report": "retries exhausted",
  "triage->report": "healthy fast path",
  "confidence_gate->acquisition": "low confidence → axial reading",
  "diag_tools->diagnostician": "tool results",
  "human_review->planner": "rejected → replan",
  "planner->report": "auto-approve (P3/P4)",
};

export const CHANNELS: { key: string; reducer: string; group: string; help: string }[] = [
  { key: "asset", reducer: "overwrite", group: "Inputs", help: "Machine metadata, bearing geometry, ISO class" },
  { key: "request", reducer: "overwrite", group: "Inputs", help: "Scenario, severity level, measurement point" },
  { key: "measurements", reducer: "append", group: "Acquisition", help: "operator.add: every reading is appended, never replaced" },
  { key: "rejected", reducer: "append", group: "Acquisition", help: "IDs of readings that failed QA" },
  { key: "pending_measurement", reducer: "overwrite", group: "Acquisition", help: "Work request for the acquisition agent" },
  { key: "acquisition_attempts", reducer: "overwrite", group: "Acquisition", help: "Retry budget counter" },
  { key: "signal_quality", reducer: "overwrite", group: "Analysis", help: "Latest QA verdict" },
  { key: "severity", reducer: "overwrite", group: "Analysis", help: "ISO 20816 zone (parallel branch A)" },
  { key: "spectral", reducer: "overwrite", group: "Analysis", help: "Order and envelope features (parallel branch B)" },
  { key: "hypotheses", reducer: "overwrite", group: "Analysis", help: "Rule-engine prior for the LLM" },
  { key: "triage", reducer: "overwrite", group: "Routing", help: "Latest supervisor decision and reason" },
  { key: "messages", reducer: "add_messages", group: "Diagnosis", help: "LLM conversation incl. tool calls; merged by message id" },
  { key: "diag_steps", reducer: "overwrite", group: "Diagnosis", help: "LLM calls in this round (loop budget)" },
  { key: "diagnosis_rounds", reducer: "overwrite", group: "Diagnosis", help: "Diagnosis rounds (incl. follow-up data)" },
  { key: "diagnosis", reducer: "overwrite", group: "Diagnosis", help: "Submitted diagnosis" },
  { key: "prognosis", reducer: "overwrite", group: "Planning", help: "Trend, model fit, RUL" },
  { key: "work_order", reducer: "overwrite", group: "Planning", help: "Work order draft (versioned by revision)" },
  { key: "review", reducer: "overwrite", group: "Planning", help: "Human decision from interrupt()" },
  { key: "plan_revisions", reducer: "overwrite", group: "Planning", help: "Replan budget counter" },
  { key: "report", reducer: "overwrite", group: "Output", help: "Final close-out" },
  { key: "agent_log", reducer: "append", group: "Output", help: "Audit trail of every agent decision" },
  { key: "llm_usage", reducer: "merge", group: "Output", help: "Custom dict-merge reducer: which agents ran live / fallback" },
];

export const FAULT_LABEL: Record<string, string> = {
  healthy: "Healthy", unbalance: "Unbalance", misalignment: "Misalignment", looseness: "Looseness",
  outer_race: "Outer race defect", inner_race: "Inner race defect",
};
