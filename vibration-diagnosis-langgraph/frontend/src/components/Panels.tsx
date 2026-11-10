import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "../api";
import { FAULT_LABEL, NODE_META } from "../meta";
import type { RunView, SignalPreview } from "../types";
import Icon from "./Icon";

const cache = new Map<string, SignalPreview>();
const AX = { stroke: "#737373", fontSize: 11 };
const TT = { contentStyle: { background: "#161616", border: "1px solid #3a3a3a", fontSize: 12 }, labelStyle: { color: "#a3a3a3" } };

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="empty">{children}</div>;
}

// ------------------------------------------------------------------ Signals
export function SignalsPanel({ view }: { view: RunView }) {
  const ms: any[] = view.values.measurements || [];
  const rejected: string[] = view.values.rejected || [];
  const [sel, setSel] = useState<string | null>(null);
  const cur = ms.find((m) => m.id === sel) || ms[ms.length - 1];
  const [prev, setPrev] = useState<SignalPreview | null>(null);
  useEffect(() => {
    if (!cur) return setPrev(null);
    const c = cache.get(cur.signal_ref);
    if (c) return setPrev(c);
    setPrev(null);
    api.signal(cur.signal_ref).then((p) => { cache.set(cur.signal_ref, p); setPrev(p); }).catch(() => setPrev(null));
  }, [cur?.signal_ref]);
  const qa = useMemo(() => {
    if (!cur) return null;
    for (let i = view.checkpoints.length - 1; i >= 0; i--) {
      const q = view.checkpoints[i].values.signal_quality;
      if (q?.measurement_id === cur.id) return q;
    }
    return null;
  }, [cur?.id, view.checkpoints.length]);
  if (!cur) return <Empty>No measurement yet. Start a run to trigger the data acquisition agent.</Empty>;
  const spec = view.values.spectral?.radial;
  const bf = spec?.bearing_freqs_hz;
  const fr = view.values.asset?.rpm / 60;
  const wf = prev ? prev.waveform.t_ms.map((t, i) => ({ t, g: prev.waveform.g[i] })) : [];
  const sp = prev ? prev.spectrum.f.map((f, i) => ({ f, v: prev.spectrum.v[i] })) : [];
  const ev = prev ? prev.envelope.f.map((f, i) => ({ f, a: prev.envelope.a[i] })) : [];
  return (
    <div className="panel-body">
      <div className="mtabs">
        {ms.map((m) => (
          <button key={m.id} className={`mtab ${cur.id === m.id ? "on" : ""} ${rejected.includes(m.id) ? "rej" : ""}`} onClick={() => setSel(m.id)}>
            <b>{m.id}</b> {m.location} · {m.direction}
            {rejected.includes(m.id) && <span className="badge red">QA reject</span>}
          </button>
        ))}
      </div>
      <div className="mmeta">
        <span>{cur.purpose}</span>
        <span className="kv"><i>v RMS</i>{cur.features.velocity_rms_mm_s} mm/s</span>
        <span className="kv"><i>a RMS</i>{cur.features.accel_rms_g} g</span>
        <span className="kv"><i>crest</i>{cur.features.crest_factor}</span>
        <span className="kv"><i>kurtosis</i>{cur.features.kurtosis}</span>
        <span className="kv"><i>fs</i>{cur.fs_hz} Hz</span>
      </div>
      {qa && (
        <div className="qa-row">
          {qa.checks.map((c: any) => (
            <span key={c.name} className={`qa ${c.ok ? "ok" : "bad"}`} title={c.value}><span className="qa-name"><Icon name={c.ok ? "check" : "cross"} size={12} /> {c.name}</span><small>{c.value}</small></span>
          ))}
        </div>
      )}
      {!prev && <Empty>Loading waveform…</Empty>}
      {prev && (
        <div className="charts">
          <div className="chart">
            <div className="chart-title">Time waveform <span className="muted">acceleration, g · first 250 ms</span></div>
            <ResponsiveContainer width="100%" height={170}>
              <LineChart data={wf} margin={{ top: 4, right: 12, bottom: 0, left: -10 }}>
                <CartesianGrid stroke="#262626" />
                <XAxis dataKey="t" type="number" domain={[0, "dataMax"]} tick={AX} unit=" ms" />
                <YAxis tick={AX} />
                <Line dataKey="g" stroke="#22d3ee" dot={false} strokeWidth={1} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="chart">
            <div className="chart-title">Velocity spectrum <span className="muted">mm/s pk · orders of running speed marked</span></div>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={sp} margin={{ top: 14, right: 12, bottom: 0, left: -10 }}>
                <CartesianGrid stroke="#262626" />
                <XAxis dataKey="f" type="number" domain={[0, Math.min(1000, Math.ceil(fr * 12))]} tick={AX} unit=" Hz" allowDataOverflow />
                <YAxis tick={AX} />
                <Tooltip {...TT} formatter={(v: any) => [`${v} mm/s`, "velocity"]} labelFormatter={(l) => `${l} Hz (${(Number(l) / fr).toFixed(2)}X)`} />
                {[0.5, 1, 2, 3, 4, 5, 6, 8, 10].map((h) => (
                  <ReferenceLine key={h} x={h * fr} stroke={h === 0.5 ? "#fb923c" : "#d4d4d4"} strokeDasharray="3 3" strokeOpacity={0.6}
                    label={{ value: `${h}X`, fill: "#d4d4d4", fontSize: 10, position: "top" }} />
                ))}
                <Line dataKey="v" stroke="#38bdf8" dot={false} strokeWidth={1.2} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="chart">
            <div className="chart-title">Envelope spectrum <span className="muted">2–5 kHz demodulated, g · bearing defect frequencies marked</span></div>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={ev} margin={{ top: 14, right: 12, bottom: 0, left: -10 }}>
                <CartesianGrid stroke="#262626" />
                <XAxis dataKey="f" type="number" domain={[0, 400]} tick={AX} unit=" Hz" allowDataOverflow />
                <YAxis tick={AX} />
                <Tooltip {...TT} formatter={(v: any) => [`${v} g`, "envelope"]} labelFormatter={(l) => `${l} Hz`} />
                {bf && (["BPFO", "BPFI", "BSF", "FTF"] as const).flatMap((k) => [1, 2, 3].map((h) => (
                  bf[k] * h <= 400 && (k === "BPFO" || k === "BPFI" || h === 1) ? (
                    <ReferenceLine key={k + h} x={bf[k] * h} stroke={k === "BPFO" ? "#f472b6" : k === "BPFI" ? "#fbbf24" : "#737373"} strokeDasharray="3 3"
                      label={h === 1 ? { value: k, fill: k === "BPFO" ? "#f472b6" : k === "BPFI" ? "#fbbf24" : "#a3a3a3", fontSize: 10, position: "top" } : undefined} />
                  ) : null
                )))}
                <Line dataKey="a" stroke="#34d399" dot={false} strokeWidth={1.2} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ Diagnosis
function ZoneBar({ sev }: { sev: any }) {
  const { "A/B": ab, "B/C": bc, "C/D": cd } = sev.limits;
  const max = cd * 1.6;
  const pct = (x: number) => `${Math.min(100, (x / max) * 100)}%`;
  return (
    <div className="zonebar">
      <div className="zb-track">
        <div className="zb z-a" style={{ width: pct(ab) }}>A</div>
        <div className="zb z-b" style={{ width: `calc(${pct(bc)} - ${pct(ab)})` }}>B</div>
        <div className="zb z-c" style={{ width: `calc(${pct(cd)} - ${pct(bc)})` }}>C</div>
        <div className="zb z-d" style={{ flex: 1 }}>D</div>
        <div className="zb-marker" style={{ left: pct(sev.velocity_rms_mm_s) }}><span>{sev.velocity_rms_mm_s} mm/s</span></div>
      </div>
      <div className="zb-labels"><span style={{ left: pct(ab) }}>{ab}</span><span style={{ left: pct(bc) }}>{bc}</span><span style={{ left: pct(cd) }}>{cd}</span></div>
    </div>
  );
}

export function DiagnosisPanel({ view }: { view: RunView }) {
  const v = view.values;
  const sev = v.severity, hyps = v.hypotheses, d = v.diagnosis, msgs: any[] = v.messages || [];
  if (!sev) return <Empty>Severity and diagnosis appear once the parallel analysis branches finish.</Empty>;
  return (
    <div className="panel-body grid2">
      <div className="card">
        <div className="card-title">ISO 20816 severity <span className={`zone-badge z-${sev.zone.toLowerCase()}`}>Zone {sev.zone}</span></div>
        <ZoneBar sev={sev} />
        <div className="muted small">{sev.standard} · governed by {sev.governing_measurement}</div>
        <div className="small">{sev.zone_text}</div>
      </div>
      <div className="card">
        <div className="card-title">Rule-engine prior <span className="muted small">(spectral agent → LLM)</span></div>
        {hyps?.map((h: any) => (
          <div key={h.fault} className="hyp">
            <span>{FAULT_LABEL[h.fault]}</span>
            <div className="hyp-bar"><div style={{ width: `${h.score * 100}%` }} /></div>
            <b>{h.score.toFixed(2)}</b>
          </div>
        ))}
        {v.triage && <div className="route-note">Supervisor: {v.triage.reason}</div>}
      </div>
      <div className="card span2">
        {!d ? <Empty>Waiting for the diagnostician…</Empty> : (
          <>
            <div className="card-title">
              Diagnosis: {d.fault_title}
              <span className={`badge ${d.mode === "live" ? "pink" : "slate"}`}>{d.mode === "live" ? "LLM (live)" : d.mode === "rules" ? "rule engine" : "rule fallback"}</span>
              <span className="badge slate">round {d.round}</span>
            </div>
            <div className="conf"><div className="conf-bar"><div style={{ width: `${d.confidence * 100}%`, background: d.confidence >= 0.7 ? "#34d399" : "#fbbf24" }} /></div><b>{Math.round(d.confidence * 100)}%</b><span className="muted small">gate threshold 70%</span></div>
            <ul className="evidence">{d.evidence.map((e: string, i: number) => <li key={i}>{e}</li>)}</ul>
            {d.rationale && <p className="small rationale">{d.rationale}</p>}
            {d.request_measurement && <div className="route-note">Requested follow-up: {d.request_measurement.direction} reading. {d.request_measurement.reason}</div>}
          </>
        )}
      </div>
      {msgs.length > 0 && (
        <div className="card span2">
          <div className="card-title">LLM tool-calling transcript <span className="muted small">state.messages · add_messages reducer</span></div>
          <div className="transcript">
            {msgs.map((m, i) => (
              <div key={i} className={`msg msg-${m.type}`}>
                <span className="msg-role">{m.type === "ai" ? "assistant" : m.type === "tool" ? `tool` : m.type}</span>
                <div>
                  {m.type === "system" ? <details><summary className="muted small">system prompt</summary><pre>{m.content}</pre></details>
                    : m.content && <pre>{m.content}</pre>}
                  {m.tool_calls?.map((t: any) => <div key={t.id} className="tcall">⚙ {t.name}({Object.keys(t.args).length ? JSON.stringify(t.args) : ""})</div>)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ Prognosis
export function PrognosisPanel({ view }: { view: RunView }) {
  const p = view.values.prognosis;
  if (!p) return <Empty>The prognosis agent runs after the diagnosis passes the confidence gate.</Empty>;
  const data = [
    ...p.trend.map((t: any) => ({ day: t.day, value: t.value })),
    ...p.forecast.map((t: any) => ({ day: t.day, forecast: t.value })),
  ];
  const yMax = Math.max(p.danger * 1.4, p.current * 1.2);
  return (
    <div className="panel-body">
      <div className="stats">
        <div className="stat"><i>{p.indicator}</i><b>{p.current} {p.unit}</b></div>
        <div className="stat"><i>growth</i><b>{(p.growth_per_day * 100).toFixed(2)} %/day</b></div>
        <div className="stat hl"><i>RUL to danger</i><b>{p.rul_days === null ? "no growth" : `${p.rul_days} days`}</b></div>
        <div className="stat"><i>95% band</i><b>{p.rul_range[0] ?? "–"} – {p.rul_range[1] ?? "–"} d</b></div>
        <div className="stat"><i>model</i><b className="mono small">{p.model}</b></div>
      </div>
      <div className="chart">
        <div className="chart-title">Trend & degradation forecast <span className="muted">120 days history, exponential fit from onset</span></div>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data} margin={{ top: 16, right: 20, bottom: 4, left: -6 }}>
            <CartesianGrid stroke="#262626" />
            <XAxis dataKey="day" type="number" domain={["dataMin", "dataMax"]} tick={AX} unit=" d" />
            <YAxis tick={AX} domain={[0, yMax]} allowDataOverflow />
            <Tooltip {...TT} />
            <ReferenceArea y1={p.alert} y2={p.danger} fill="#fbbf24" fillOpacity={0.06} />
            <ReferenceArea y1={p.danger} y2={yMax} fill="#ef4444" fillOpacity={0.07} />
            <ReferenceLine y={p.alert} stroke="#fbbf24" strokeDasharray="4 4" label={{ value: `alert ${p.alert}`, fill: "#fbbf24", fontSize: 11, position: "insideTopLeft" }} />
            <ReferenceLine y={p.danger} stroke="#ef4444" strokeDasharray="4 4" label={{ value: `danger ${p.danger}`, fill: "#ef4444", fontSize: 11, position: "insideTopLeft" }} />
            <ReferenceLine x={0} stroke="#a3a3a3" label={{ value: "today", fill: "#a3a3a3", fontSize: 11, position: "top" }} />
            <ReferenceLine x={p.onset_day} stroke="#737373" strokeDasharray="2 4" label={{ value: "onset", fill: "#737373", fontSize: 11, position: "top" }} />
            {p.rul_days !== null && p.rul_days > 0 && <ReferenceLine x={p.rul_days} stroke="#ef4444" label={{ value: `RUL ${p.rul_days} d`, fill: "#ef4444", fontSize: 11, position: "top" }} />}
            <Line dataKey="value" stroke="#22d3ee" dot={false} strokeWidth={1.5} isAnimationActive={false} connectNulls={false} />
            <Line dataKey="forecast" stroke="#f472b6" dot={false} strokeWidth={2} strokeDasharray="6 4" isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Work order + approval
export function WorkOrderPanel({ view, onResume }: { view: RunView; onResume: (b: object) => Promise<void> }) {
  const wo = view.values.work_order, review = view.values.review;
  const [comment, setComment] = useState("");
  const [reviewer, setReviewer] = useState("R. Engineer");
  const [busy, setBusy] = useState(false);
  if (!wo) return <Empty>The maintenance planner drafts a work order after prognosis.</Empty>;
  const waiting = view.status === "interrupted";
  const send = async (decision: string) => {
    setBusy(true);
    try { await onResume({ decision, comment, reviewer }); setComment(""); } finally { setBusy(false); }
  };
  return (
    <div className="panel-body">
      {waiting && (
        <div className="approval">
          <div className="ap-head"><Icon name="human" size={15} /> Human-in-the-loop: graph paused at <code>interrupt()</code></div>
          <div className="small">{view.interrupt?.question ?? `Approve ${wo.id}?`} The checkpoint is saved; nothing runs until you answer. Your answer is sent as <code>Command(resume=…)</code>.</div>
          <div className="ap-form">
            <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="Reviewer" />
            <textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Comment (required to reject, e.g. 'Schedule during Saturday shutdown and add coupling inspection')" rows={2} />
            <div className="ap-btns">
              <button className="btn primary" disabled={busy} onClick={() => send("approve")}>Approve & release</button>
              {view.interrupt?.allow_reject !== false && (
                <button className="btn warn" disabled={busy || !comment.trim()} onClick={() => send("reject")}>Reject → replan</button>
              )}
            </div>
          </div>
        </div>
      )}
      <div className="wo">
        <div className="wo-head">
          <div>
            <div className="muted small">{wo.id} · revision {wo.revision} · {wo.mode === "live" ? "drafted by LLM" : wo.mode === "fallback" ? "template (LLM fallback)" : "template (rule mode)"}</div>
            <h3>{wo.title}</h3>
          </div>
          <div className={`prio prio-${wo.priority}`}>{wo.priority}<small>due ≤ {wo.due_within_days} d</small></div>
        </div>
        {wo.guardrail && <div className="route-note warn">🛡 {wo.guardrail}</div>}
        <p className="small">{wo.justification}</p>
        <div className="grid2">
          <div>
            <div className="sub-title">Tasks</div>
            <ol className="tasks">{wo.tasks.map((t: string, i: number) => <li key={i}>{t}</li>)}</ol>
          </div>
          <div>
            <div className="sub-title">Parts</div>
            <table className="tbl"><thead><tr><th>Part</th><th>On hand</th><th>Location</th></tr></thead>
              <tbody>{wo.parts.map((p: any) => <tr key={p.part}><td>{p.part}</td><td className={p.on_hand === 0 ? "bad" : ""}>{p.on_hand ?? "?"}{p.on_hand === 0 && p.lead_time_days ? ` (lead ${p.lead_time_days} d)` : ""}</td><td>{p.location}</td></tr>)}</tbody></table>
            <div className="sub-title">Crew & safety</div>
            <div className="chips">{wo.skills.map((s: string) => <span key={s} className="pill">{s}</span>)}<span className="pill">{wo.estimated_hours} h</span></div>
            <div className="chips">{wo.safety.map((s: string) => <span key={s} className="pill warn">{s}</span>)}</div>
          </div>
        </div>
        {review && (
          <div className={`route-note ${review.decision === "approve" ? "ok" : "warn"}`}>
            <Icon name={review.decision === "approve" ? "check" : "cross"} size={13} /> {review.decision === "approve" ? "Approved" : "Rejected"} by {review.reviewer} ({review.work_order_id}){review.comment ? `: "${review.comment}"` : ""}
          </div>
        )}
        {!wo.requires_approval && <div className="route-note ok">Auto-approved by policy ({wo.priority} does not need sign-off).</div>}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Report
export function ReportPanel({ view }: { view: RunView }) {
  const r = view.values.report;
  const path = Object.keys(view.stepTasks).map(Number).sort((a, b) => a - b).map((s) => view.stepTasks[s]);
  if (!r) return <Empty>The report agent closes out the run.</Empty>;
  return (
    <div className="panel-body">
      <div className={`report-banner st-${r.status}`}>
        <div className="rb-status">{r.status.replace("_", " ")}</div>
        <div className="rb-head">{r.headline}</div>
      </div>
      <div className="sub-title">Execution path ({path.length - 1} super-steps)</div>
      <div className="path">
        {path.map((nodes, i) => (
          <span key={i} className="path-step">{nodes.map((n) => NODE_META[n]?.label ?? n).join(" ∥ ")}</span>
        ))}
        <span className="path-step">END</span>
      </div>
      <div className="grid2">
        <div className="card">
          <div className="card-title">Run facts</div>
          <table className="tbl">
            <tbody>
              <tr><td>Thread</td><td className="mono">{view.threadId}</td></tr>
              <tr><td>Checkpoints written</td><td>{view.checkpoints.length}</td></tr>
              <tr><td>Measurements</td><td>{(view.values.measurements || []).length} ({(view.values.rejected || []).length} rejected)</td></tr>
              <tr><td>Diagnosis rounds</td><td>{view.values.diagnosis_rounds ?? 0}</td></tr>
              <tr><td>LLM messages</td><td>{(view.values.messages || []).length}</td></tr>
              <tr><td>Plan revisions</td><td>{view.values.plan_revisions ?? 0}</td></tr>
            </tbody>
          </table>
        </div>
        <div className="card">
          <div className="card-title">Agent execution mode</div>
          <table className="tbl"><tbody>
            {Object.entries(view.values.llm_usage || {}).map(([a, m]) => <tr key={a}><td>{NODE_META[a]?.label ?? a}</td><td>{String(m)}</td></tr>)}
            {Object.keys(view.values.llm_usage || {}).length === 0 && <tr><td colSpan={2} className="muted">Healthy fast path: no LLM agent was needed.</td></tr>}
          </tbody></table>
        </div>
      </div>
    </div>
  );
}
