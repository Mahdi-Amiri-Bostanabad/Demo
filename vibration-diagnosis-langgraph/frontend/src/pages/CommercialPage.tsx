import type React from "react";
import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { api } from "../api";
import GraphView from "../components/GraphView";
import Icon from "../components/Icon";
import ReportToast, { downloadReport } from "../components/ReportToast";
import { NODE_META } from "../meta";
import { useRun } from "../runStore";
import type { Asset, Meta, RunView, SignalPreview, Topology } from "../types";

// Commercial mode: a showcase page. Few words; the problem, the input, the agent graph and the
// engineering diagrams carry the story. Everything comes from the same run/SSE stream as dev mode.

const SHORT: Record<string, string> = {
  healthy: "Healthy", unbalance: "Unbalance", misalignment: "Misalignment", looseness: "Looseness",
  outer_race: "Outer race", inner_race: "Inner race", sensor_fault: "Loose sensor",
};
const FAULT_TITLE: Record<string, string> = {
  healthy: "Healthy", unbalance: "Rotor unbalance", misalignment: "Shaft misalignment", looseness: "Mechanical looseness",
  outer_race: "Bearing outer race defect", inner_race: "Bearing inner race defect",
};
const ZONE_COLOR: Record<string, string> = { A: "#34d399", B: "#a3e635", C: "#fbbf24", D: "#ef4444" };
const AX = { stroke: "#5c5c5c", fontSize: 10 };
const yfmt = (v: number) => (v === 0 ? "0" : Math.abs(v) >= 10 ? v.toFixed(0) : Math.abs(v) >= 1 ? v.toFixed(1) : String(Number(v.toPrecision(1))));
const LIME = "#dafa9c";
const cache = new Map<string, SignalPreview>();

// ---------------------------------------------------------------- machine schematic (the "problem")

function MachineSchematic({ asset, view, location }: { asset?: Asset; view: RunView; location: string }) {
  const v = view.values;
  const zone: string | undefined = v.severity?.zone;
  const fault: string | undefined = v.diagnosis?.primary_fault;
  const ms: any[] = v.measurements || [];
  const last = ms[ms.length - 1];
  const axial = last?.direction === "Axial";
  const kind = asset?.type.toLowerCase().includes("fan") ? "fan" : asset?.type.toLowerCase().includes("compressor") ? "comp" : "pump";
  const points = asset?.measurement_points ?? ["Motor NDE", "Motor DE", "Pump DE", "Pump NDE"];
  const px = [96, 214, 330, 452];
  const sx = px[Math.max(0, points.indexOf(last?.location ?? location))];
  const hot = (part: string) => {
    if (!fault || fault === "healthy") return false;
    if (part === "rotor") return fault === "unbalance";
    if (part === "coupling") return fault === "misalignment";
    if (part === "base") return fault === "looseness";
    if (part === "bearing") return fault === "outer_race" || fault === "inner_race";
    return false;
  };
  const shake = view.status === "running" || view.status === "interrupted" ? `shake-${(zone ?? "B").toLowerCase()}` : "";
  const fault_c = "#ef4444";
  const stroke = "#5c5c5c";
  return (
    <svg viewBox="0 0 540 230" className="cm-machine" role="img" aria-label={`${asset?.name ?? "Machine"} schematic`}>
      <defs>
        <pattern id="hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="8" stroke="#262626" strokeWidth="3" />
        </pattern>
      </defs>
      {/* foundation */}
      <rect x="40" y="186" width="460" height="22" rx="3" fill="url(#hatch)" stroke={hot("base") ? fault_c : stroke} strokeWidth={hot("base") ? 2 : 1} className={hot("base") ? "cm-hot" : ""} />
      <g className={shake}>
        {/* motor */}
        <rect x="70" y="80" width="170" height="92" rx="10" fill="#1a1a1a" stroke={stroke} />
        {[0, 1, 2, 3, 4, 5, 6].map((i) => <line key={i} x1={96 + i * 20} y1="80" x2={96 + i * 20} y2="172" stroke="#262626" />)}
        <text x="155" y="131" textAnchor="middle" className="cm-svg-label">MOTOR</text>
        <rect x="60" y="172" width="190" height="14" fill="#1a1a1a" stroke={stroke} />
        {/* shaft + coupling */}
        <line x1="240" y1="126" x2="306" y2="126" stroke="#8f8f8f" strokeWidth="6" />
        <rect x="262" y="108" width="22" height="36" rx="4" fill={hot("coupling") ? "#3b1212" : "#202020"} stroke={hot("coupling") ? fault_c : "#8f8f8f"} strokeWidth={hot("coupling") ? 2 : 1} className={hot("coupling") ? "cm-hot" : ""} />
        {/* driven machine */}
        {kind === "pump" && <>
          <circle cx="392" cy="122" r="50" fill="#1a1a1a" stroke={hot("rotor") ? fault_c : stroke} strokeWidth={hot("rotor") ? 2 : 1} className={hot("rotor") ? "cm-hot" : ""} />
          <circle cx="392" cy="122" r="22" fill="none" stroke="#333" />
          <rect x="420" y="54" width="26" height="30" fill="#1a1a1a" stroke={stroke} />
          <text x="392" y="126" textAnchor="middle" className="cm-svg-label">PUMP</text>
        </>}
        {kind === "fan" && <>
          <circle cx="392" cy="120" r="56" fill="#1a1a1a" stroke={hot("rotor") ? fault_c : stroke} strokeWidth={hot("rotor") ? 2 : 1} className={hot("rotor") ? "cm-hot" : ""} />
          <g className={view.status === "running" ? "cm-spin" : ""} style={{ transformOrigin: "392px 120px" }}>
            {[0, 60, 120, 180, 240, 300].map((a) => <line key={a} x1="392" y1="120" x2={392 + 46 * Math.cos((a * Math.PI) / 180)} y2={120 + 46 * Math.sin((a * Math.PI) / 180)} stroke="#474747" strokeWidth="5" />)}
          </g>
          <text x="392" y="196" textAnchor="middle" className="cm-svg-label">FAN</text>
        </>}
        {kind === "comp" && <>
          <rect x="320" y="74" width="150" height="98" rx="10" fill="#1a1a1a" stroke={hot("rotor") ? fault_c : stroke} strokeWidth={hot("rotor") ? 2 : 1} className={hot("rotor") ? "cm-hot" : ""} />
          <path d="M335 105 q15 -12 30 0 t30 0 t30 0 t30 0 M335 140 q15 -12 30 0 t30 0 t30 0 t30 0" fill="none" stroke="#474747" strokeWidth="3" />
          <text x="395" y="127" textAnchor="middle" className="cm-svg-label">COMPRESSOR</text>
        </>}
        <rect x="320" y="172" width="150" height="14" fill="#1a1a1a" stroke={stroke} />
        {/* bearings */}
        {px.map((x, i) => {
          const h = hot("bearing") && Math.abs(x - sx) < 1;
          return <circle key={i} cx={x} cy={i < 2 ? 126 : 126} r="7" fill={h ? "#3b1212" : "#0f0f0f"} stroke={h ? fault_c : "#8f8f8f"} strokeWidth={h ? 2 : 1} className={h ? "cm-hot" : ""} />;
        })}
      </g>
      {/* sensor */}
      {(last || view.status === "idle") && (
        <g className="cm-sensor" style={{ transform: `translate(${sx}px, ${axial ? 126 : 66}px)` }}>
          {axial
            ? <><rect x="-34" y="-9" width="18" height="18" rx="3" fill={LIME} /><path d="M-14 0h-30" stroke={LIME} strokeWidth="1.5" strokeDasharray="3 3" /></>
            : <><rect x="-9" y="-12" width="18" height="18" rx="3" fill={LIME} /><path d="M0 6v38" stroke={LIME} strokeWidth="1.5" strokeDasharray="3 3" /></>}
        </g>
      )}
      <text x="40" y="24" className="cm-svg-cap">{asset?.id}</text>
      <text x="40" y="42" className="cm-svg-sub">{asset ? `${asset.rpm} rpm · ${asset.bearing.model}` : ""}</text>
      {zone && <g transform="translate(470, 16)"><rect width="34" height="26" rx="6" fill={ZONE_COLOR[zone]} /><text x="17" y="18" textAnchor="middle" className="cm-svg-zone">{zone}</text></g>}
    </svg>
  );
}

// ---------------------------------------------------------------- diagrams

function Card({ title, value, children, empty }: { title: string; value?: React.ReactNode; children: React.ReactNode; empty: boolean }) {
  return (
    <section className={`cm-card ${empty ? "is-empty" : ""}`}>
      <header><span>{title}</span>{value !== undefined && <b>{value}</b>}</header>
      <div className="cm-card-body">{empty ? <div className="cm-wait" /> : children}</div>
    </section>
  );
}

function Spectrum({ prev, fr }: { prev: SignalPreview; fr: number }) {
  const data = prev.spectrum.f.map((f, i) => ({ f, v: prev.spectrum.v[i] }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 14, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="#1f1f1f" vertical={false} />
        <XAxis dataKey="f" type="number" domain={[0, Math.ceil(fr * 10.5)]} tick={AX} allowDataOverflow tickFormatter={(x) => `${x}`} />
        <YAxis tick={AX} tickFormatter={yfmt} width={44} />
        {[1, 2, 3].map((h) => <ReferenceLine key={h} x={h * fr} stroke="#474747" strokeDasharray="2 3" label={{ value: `${h}X`, fill: "#8f8f8f", fontSize: 10, position: "top" }} />)}
        <Line dataKey="v" stroke={LIME} dot={false} strokeWidth={1.3} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

function Envelope({ prev, bf }: { prev: SignalPreview; bf: any }) {
  const data = prev.envelope.f.map((f, i) => ({ f, a: prev.envelope.a[i] }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 14, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="#1f1f1f" vertical={false} />
        <XAxis dataKey="f" type="number" domain={[0, 400]} tick={AX} allowDataOverflow />
        <YAxis tick={AX} tickFormatter={yfmt} width={44} />
        {bf && <ReferenceLine x={bf.BPFO} stroke="#f472b6" strokeDasharray="2 3" label={{ value: "BPFO", fill: "#f472b6", fontSize: 10, position: "top" }} />}
        {bf && <ReferenceLine x={bf.BPFI} stroke="#fbbf24" strokeDasharray="2 3" label={{ value: "BPFI", fill: "#fbbf24", fontSize: 10, position: "top" }} />}
        <Line dataKey="a" stroke={LIME} dot={false} strokeWidth={1.3} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

function ZoneGauge({ sev }: { sev: any }) {
  const { "A/B": ab, "B/C": bc, "C/D": cd } = sev.limits;
  const max = cd * 1.5;
  const x = (val: number) => 20 + Math.min(1, val / max) * 280;
  const segs = [["A", 0, ab], ["B", ab, bc], ["C", bc, cd], ["D", cd, max]] as const;
  return (
    <svg viewBox="0 0 320 120" className="cm-gauge" role="img" aria-label={`ISO zone ${sev.zone}`}>
      {segs.map(([z, a, b]) => (
        <g key={z}>
          <rect x={x(a)} y="52" width={x(b) - x(a) - 2} height="22" rx="4" fill={ZONE_COLOR[z]} opacity={z === sev.zone ? 1 : 0.22} />
          <text x={(x(a) + x(b)) / 2} y="67" textAnchor="middle" className="cm-svg-zone small">{z}</text>
        </g>
      ))}
      <g className="cm-needle" style={{ transform: `translateX(${x(sev.velocity_rms_mm_s)}px)` }}>
        <path d="M0 44 L-6 34 L6 34 Z" fill="#f2f2f2" />
        <line x1="0" y1="44" x2="0" y2="82" stroke="#f2f2f2" strokeWidth="2" />
      </g>
      {[ab, bc, cd].map((l) => <text key={l} x={x(l)} y="94" textAnchor="middle" className="cm-svg-tick">{l}</text>)}
      <text x="300" y="112" textAnchor="end" className="cm-svg-tick">mm/s RMS · ISO 20816</text>
    </svg>
  );
}

function Trend({ p }: { p: any }) {
  const data = [...p.trend.map((t: any) => ({ d: t.day, y: t.value })), ...p.forecast.map((t: any) => ({ d: t.day, f: t.value }))];
  const yMax = Math.max(p.danger * 1.3, p.current * 1.15);
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 14, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="#1f1f1f" vertical={false} />
        <XAxis dataKey="d" type="number" domain={["dataMin", "dataMax"]} tick={AX} />
        <YAxis tick={AX} domain={[0, yMax]} allowDataOverflow tickFormatter={yfmt} width={44} />
        <ReferenceArea y1={p.danger} y2={yMax} fill="#ef4444" fillOpacity={0.08} />
        <ReferenceLine y={p.danger} stroke="#ef4444" strokeDasharray="3 3" />
        <ReferenceLine x={0} stroke="#5c5c5c" />
        {p.rul_days > 0 && <ReferenceLine x={p.rul_days} stroke="#ef4444" label={{ value: `${p.rul_days} d`, fill: "#ef4444", fontSize: 10, position: "top" }} />}
        <Line dataKey="y" stroke="#8f8f8f" dot={false} strokeWidth={1.2} isAnimationActive={false} />
        <Line dataKey="f" stroke={LIME} dot={false} strokeWidth={2} strokeDasharray="5 4" isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------- page

export default function CommercialPage({ modeSwitch }: { modeSwitch: React.ReactNode }) {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [topo, setTopo] = useState<Topology | null>(null);
  const { view, attach } = useRun(topo);
  const [assetId, setAssetId] = useState("P-101");
  const [scenario, setScenario] = useState("misalignment");
  const [prev, setPrev] = useState<SignalPreview | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    Promise.all([api.meta(), api.graph()]).then(([m, g]) => { setMeta(m); setTopo(g); }).catch(() => {});
  }, []);
  useEffect(() => {
    if (!topo) return;
    const r = new URLSearchParams(window.location.search).get("run");
    if (r) attach(r);
  }, [topo]);
  useEffect(() => { if (view.threadId) history.replaceState(null, "", `?run=${view.threadId}`); }, [view.threadId]);
  // a run opened by link: show its asset and scenario in the input
  useEffect(() => {
    if (view.meta?.asset_id) setAssetId(view.meta.asset_id);
    if (view.meta?.scenario) setScenario(view.meta.scenario);
  }, [view.meta?.asset_id, view.meta?.scenario]);

  const v = view.values;
  const ms: any[] = v.measurements || [];
  const rej: string[] = v.rejected || [];
  const radial = [...ms].reverse().find((m) => m.direction !== "Axial" && !rej.includes(m.id));
  useEffect(() => {
    if (!radial) return setPrev(null);
    const c = cache.get(radial.signal_ref);
    if (c) return setPrev(c);
    api.signal(radial.signal_ref).then((p) => { cache.set(radial.signal_ref, p); setPrev(p); }).catch(() => {});
  }, [radial?.signal_ref]);

  const asset = meta?.assets.find((a) => a.id === assetId);
  const running = view.status === "running";
  const start = async () => {
    if (!asset) return;
    const { thread_id } = await api.start({ asset_id: assetId, scenario, level: "moderate", location: asset.measurement_points[2], use_llm: true, pace: 0.8 });
    attach(thread_id);
  };
  const answer = async (decision: string) => {
    if (!view.threadId) return;
    setBusy(true);
    try { await api.resume(view.threadId, { decision, comment: reason, reviewer: "Reliability engineer" }); setReason(""); } finally { setBusy(false); }
  };

  const active = Object.entries(view.nodeStatus).filter(([n, s]) => s === "active" && NODE_META[n]).map(([n]) => NODE_META[n].label);
  const d = v.diagnosis, sev = v.severity, p = v.prognosis, wo = v.work_order, rep = v.report;
  const fr = (asset?.rpm ?? 1780) / 60;
  const bf = v.spectral?.radial?.bearing_freqs_hz;
  const healthy = rep?.status === "healthy";
  const statusLine = running ? (active.join(" + ") || "Working") : view.status === "interrupted" ? "Awaiting approval" : view.status === "done" ? "Complete" : "";

  return (
    <div className="cm">
      <header className="cm-head">
        <div className="brand">
          <svg width="24" height="24" viewBox="0 0 32 32" aria-hidden="true"><path d="M2 16h5l3-9 5 18 4-14 3 5h8" fill="none" stroke={LIME} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /></svg>
          <div className="b1">Vibration Diagnosis</div>
        </div>
        <div className="hdr-right">
          {meta && <span className={`cm-ai ${meta.llm.available ? "on" : "off"}`} title={meta.llm.available ? `LLM live · ${meta.llm.model}` : "LLM offline · rule fallback"}><span className="llm-dot" />AI</span>}
          {modeSwitch}
        </div>
      </header>

      <main className="cm-main">
        <div className="cm-top">
          <div className="cm-left">
            <section className="cm-panel cm-input" aria-label="Input">
              <div className="cm-assets" role="group" aria-label="Machine">
                {meta?.assets.map((a) => (
                  <button type="button" key={a.id} aria-pressed={a.id === assetId} className={a.id === assetId ? "on" : ""} disabled={running} onClick={() => setAssetId(a.id)}>
                    <b>{a.id}</b><small>{a.name.replace(a.id, "").replace(/(Cooling Water |Induced Draft |Process Air )/, "").trim()}</small>
                  </button>
                ))}
              </div>
              <div className="cm-faults" role="group" aria-label="Simulated fault">
                {meta?.scenarios.map((s) => (
                  <button type="button" key={s.id} aria-pressed={s.id === scenario} className={s.id === scenario ? "on" : ""} disabled={running} onClick={() => setScenario(s.id)} title={s.blurb}>
                    {SHORT[s.id] ?? s.label}
                  </button>
                ))}
              </div>
              <button type="button" className="btn primary cm-run" onClick={start} disabled={!meta || running}>
                {running ? <><i className="spin" /> Diagnosing</> : <><Icon name="play" size={14} /> Run</>}
              </button>
            </section>
            <section className="cm-panel cm-machine-wrap" aria-label="Machine">
              <MachineSchematic asset={asset} view={view} location={asset?.measurement_points[2] ?? ""} />
              {statusLine && <div className={`cm-status st-${view.status}`}>{running && <i className="spin" />}{statusLine}</div>}
            </section>
          </div>
          <section className="cm-panel cm-graph" aria-label="Agent graph">
            <GraphView topo={topo} view={view} />
          </section>
        </div>

        {(d || healthy || view.status === "interrupted") && (
          <section className={`cm-verdict ${healthy ? "ok" : ""}`} aria-live="polite">
            <div className="cm-v-main">
              <span className="cm-v-label">{healthy ? "Healthy" : d ? (FAULT_TITLE[d.primary_fault] ?? d.fault_title) : ""}</span>
              {d && !healthy && <span className="cm-v-conf">{Math.round(d.confidence * 100)}%</span>}
            </div>
            <div className="cm-v-facts">
              {sev && <span><i>Zone</i><b style={{ color: ZONE_COLOR[sev.zone] }}>{sev.zone}</b></span>}
              {p && <span><i>RUL</i><b>{p.rul_days === null ? "stable" : `${p.rul_days} d`}</b></span>}
              {wo && <span><i>{wo.id}</i><b className={`prio-text p-${wo.priority}`}>{wo.priority}</b></span>}
            </div>
            {view.status === "interrupted" ? (
              <div className="cm-approve">
                <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Note (optional)" aria-label="Reviewer note" />
                <button type="button" className="btn" disabled={busy || !reason.trim()} onClick={() => answer("reject")}>Revise</button>
                <button type="button" className="btn primary" disabled={busy} onClick={() => answer("approve")}><Icon name="check" size={14} /> Approve</button>
              </div>
            ) : (
              <div className="cm-done">
                {v.review?.decision === "approve" && <><Icon name="check" size={14} /> Approved</>}
                {view.status === "done" && view.threadId && (
                  <button type="button" className="btn cm-report-btn" onClick={() => downloadReport(view.threadId!)}><Icon name="download" size={14} /> Report</button>
                )}
              </div>
            )}
          </section>
        )}

        <div className="cm-charts">
          <Card title="Spectrum" value={radial ? `${radial.features.velocity_rms_mm_s} mm/s` : undefined} empty={!prev}>{prev && <Spectrum prev={prev} fr={fr} />}</Card>
          <Card title="Envelope" value={radial ? `kurtosis ${radial.features.kurtosis}` : undefined} empty={!prev}>{prev && <Envelope prev={prev} bf={bf} />}</Card>
          <Card title="Severity" value={sev ? `Zone ${sev.zone}` : undefined} empty={!sev}>{sev && <ZoneGauge sev={sev} />}</Card>
          <Card title="Remaining life" value={p ? (p.rul_days === null ? "stable" : `${p.rul_days} days`) : undefined} empty={!p}>{p && <Trend p={p} />}</Card>
        </div>
      </main>
      <ReportToast view={view} />
    </div>
  );
}
