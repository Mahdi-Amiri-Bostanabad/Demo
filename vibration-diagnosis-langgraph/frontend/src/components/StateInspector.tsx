import { useState } from "react";
import { CHANNELS, NODE_META } from "../meta";
import type { Checkpoint, RunView } from "../types";

function JsonTree({ v, depth = 0, name }: { v: any; depth?: number; name?: string }) {
  const [open, setOpen] = useState(depth < 1);
  const isObj = v && typeof v === "object";
  if (!isObj) {
    const cls = typeof v === "number" ? "jn" : typeof v === "string" ? "js" : "jb";
    const s = typeof v === "string" ? `"${v.length > 160 ? v.slice(0, 160) + "…" : v}"` : String(v);
    return <div className="jrow">{name !== undefined && <span className="jk">{name}: </span>}<span className={cls}>{s}</span></div>;
  }
  const entries = Array.isArray(v) ? v.map((x, i) => [String(i), x] as const) : Object.entries(v);
  const shown = entries.slice(0, 25);
  return (
    <div className="jrow">
      <button type="button" className="jtoggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "▾" : "▸"} {name !== undefined && <span className="jk">{name}: </span>}
        <span className="jmeta">{Array.isArray(v) ? `[${v.length}]` : `{${entries.length}}`}</span>
      </button>
      {open && (
        <div className="jchildren">
          {shown.map(([k, x]) => <JsonTree key={k} v={x} depth={depth + 1} name={k} />)}
          {entries.length > shown.length && <div className="jmeta">… {entries.length - shown.length} more</div>}
        </div>
      )}
    </div>
  );
}

function summary(key: string, v: any): string {
  if (v === undefined) return "—";
  if (v === null) return "null";
  try {
    switch (key) {
      case "asset": return `${v.id} · ${v.rpm} rpm · ${v.bearing?.model}`;
      case "request": return `${v.scenario} · ${v.level} · ${v.location}`;
      case "measurements": return `${v.length} · ` + v.map((m: any) => `${m.id} ${m.direction}`).join(", ");
      case "rejected": return v.length ? v.join(", ") : "[]";
      case "signal_quality": return `${v.measurement_id}: ${v.verdict.toUpperCase()}`;
      case "severity": return `${v.velocity_rms_mm_s} mm/s · Zone ${v.zone}`;
      case "spectral": return `radial ${v.radial?.measurement_id ?? "-"}${v.axial ? ` + axial ${v.axial.measurement_id}` : ""}`;
      case "hypotheses": return v.slice(0, 3).map((h: any) => `${h.fault} ${h.score}`).join(" · ");
      case "triage": return `→ ${v.route}`;
      case "messages": return `${v.length} msgs · ${v.filter((m: any) => m.type === "tool").length} tool results`;
      case "diagnosis": return `${v.primary_fault} @ ${v.confidence} (${v.mode})`;
      case "prognosis": return `RUL ${v.rul_days ?? "∞"} d · ${v.indicator}`;
      case "work_order": return `${v.id} r${v.revision} · ${v.priority} · ${v.due_within_days} d`;
      case "review": return `${v.decision} by ${v.reviewer}`;
      case "report": return `${v.status}`;
      case "agent_log": return `${v.length} entries`;
      case "llm_usage": return Object.entries(v).map(([a, m]) => `${a}:${m}`).join(" · ") || "{}";
    }
  } catch { /* fall through */ }
  const s = JSON.stringify(v);
  return s.length > 60 ? s.slice(0, 60) + "…" : s;
}

export default function StateInspector({ view, selected }: { view: RunView; selected: number | null }) {
  const [openKey, setOpenKey] = useState<string | null>(null);
  const cps = view.checkpoints;
  const idx = selected ?? cps.length - 1;
  const cp: Checkpoint | undefined = cps[idx];
  const prev = idx > 0 ? cps[idx - 1] : undefined;
  if (!cp) return <div className="empty">State appears here as soon as the graph writes its first checkpoint.</div>;
  const writers = view.stepTasks[cp.step] || [];
  const changed = (k: string) => JSON.stringify(cp.values[k]) !== JSON.stringify(prev?.values[k]);
  let group = "";
  return (
    <div className="inspector">
      <div className="cp-head">
        <div><span className="muted">checkpoint</span> <code>{cp.checkpoint_id?.slice(-12)}</code></div>
        <div><span className="muted">step</span> <b>{cp.step}</b> <span className="muted">· {cp.source}</span></div>
        <div><span className="muted">written by</span> {writers.length ? writers.map((w) => <span key={w} className="pill">{NODE_META[w]?.label ?? w}</span>) : <span className="muted">input</span>}</div>
        <div><span className="muted">next</span> {cp.next.length ? cp.next.map((w) => <span key={w} className="pill next">{NODE_META[w]?.label ?? w}</span>) : <span className="pill">END</span>}</div>
      </div>
      {CHANNELS.map((c) => {
        const v = cp.values[c.key];
        const ch = changed(c.key);
        const header = c.group !== group ? (group = c.group) : null;
        return (
          <div key={c.key}>
            {header && <div className="ch-group">{header}</div>}
            <button type="button" aria-expanded={openKey === c.key} className={`ch-row ${ch ? "changed" : ""} ${v === undefined ? "unset" : ""}`} onClick={() => setOpenKey(openKey === c.key ? null : c.key)} title={c.help}>
              <span className="ch-key">{c.key}</span>
              <span className={`red red-${c.reducer}`}>{c.reducer}</span>
              <span className="ch-sum">{summary(c.key, v)}</span>
              {ch ? <span className="ch-dot" title="changed in this step" /> : <span />}
            </button>
            {openKey === c.key && v !== undefined && (
              <div className="ch-json"><div className="muted small">{c.help}{view.lastWriter[c.key] ? ` · last written by ${view.lastWriter[c.key].node}` : ""}</div><JsonTree v={v} /></div>
            )}
          </div>
        );
      })}
    </div>
  );
}
