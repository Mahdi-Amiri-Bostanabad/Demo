import type React from "react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import ActivityFeed from "../components/ActivityFeed";
import GraphView from "../components/GraphView";
import { DiagnosisPanel, PrognosisPanel, ReportPanel, SignalsPanel, WorkOrderPanel } from "../components/Panels";
import StateInspector from "../components/StateInspector";
import Timeline from "../components/Timeline";
import Icon from "../components/Icon";
import ReportToast, { downloadReport } from "../components/ReportToast";
import { useRun } from "../runStore";
import type { Meta, Topology } from "../types";

const TABS = ["Signals", "Diagnosis", "Prognosis", "Work order", "Report"] as const;
type Tab = (typeof TABS)[number];
const TAB_FOR_NODE: Record<string, Tab> = {
  acquisition: "Signals", signal_qa: "Signals", severity: "Diagnosis", spectral: "Signals", triage: "Diagnosis",
  diagnostician: "Diagnosis", diag_tools: "Diagnosis", confidence_gate: "Diagnosis", prognosis: "Prognosis",
  planner: "Work order", human_review: "Work order", report: "Report",
};

export default function DevPage({ modeSwitch }: { modeSwitch: React.ReactNode }) {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [topo, setTopo] = useState<Topology | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const { view, attach } = useRun(topo);
  const [assetId, setAssetId] = useState("P-101");
  const [scenario, setScenario] = useState("misalignment");
  const [level, setLevel] = useState("moderate");
  const [location, setLocation] = useState("");
  const [useLlm, setUseLlm] = useState(true);
  const [pace, setPace] = useState(0.8);
  const [tab, setTab] = useState<Tab>("Signals");
  const [follow, setFollow] = useState(true);
  const [side, setSide] = useState<"state" | "activity">("activity");
  const [selCp, setSelCp] = useState<number | null>(null);
  const [runs, setRuns] = useState<any[]>([]);

  useEffect(() => {
    Promise.all([api.meta(), api.graph()]).then(([m, g]) => { setMeta(m); setTopo(g); }).catch((e) => setErr(String(e)));
    api.runs().then(setRuns).catch(() => {});
  }, []);
  // deep link: ?run=<thread_id>&tab=<Tab>&side=state  (survives reloads, handy for sharing a run)
  useEffect(() => {
    if (!topo) return;
    const q = new URLSearchParams(window.location.search);
    const r = q.get("run");
    if (r) attach(r);
    const t = q.get("tab") as Tab | null;
    if (t && TABS.includes(t)) { setTab(t); setFollow(false); }
    if (q.get("side") === "state") setSide("state");
  }, [topo]);
  useEffect(() => {
    if (view.threadId) history.replaceState(null, "", `?run=${view.threadId}`);
  }, [view.threadId]);
  const asset = meta?.assets.find((a) => a.id === assetId);
  useEffect(() => { if (asset) setLocation(asset.measurement_points[2]); }, [assetId, meta]);

  // follow the active agent with the main tab
  const activeNodes = Object.entries(view.nodeStatus).filter(([, s]) => s === "active" || s === "interrupted").map(([n]) => n);
  const activeKey = activeNodes.join(",");
  useEffect(() => {
    if (!follow || !activeNodes.length) return;
    const t = TAB_FOR_NODE[activeNodes[activeNodes.length - 1]];
    if (t) setTab(t);
  }, [activeKey, follow]);
  useEffect(() => { if (view.status !== "running") api.runs().then(setRuns).catch(() => {}); }, [view.status]);

  const start = async () => {
    setErr(null); setSelCp(null);
    try {
      const { thread_id } = await api.start({ asset_id: assetId, scenario, level, location, use_llm: useLlm, pace });
      attach(thread_id);
      setTab("Signals");
    } catch (e) { setErr(String(e)); }
  };
  const resume = async (b: object) => {
    if (!view.threadId) return;
    await api.resume(view.threadId, b);
  };
  // keep the LLM pill honest: AvalAI comes and goes, so refresh it every 30 s
  useEffect(() => {
    const id = setInterval(() => {
      api.llm().then((s) => setMeta((m) => (m ? { ...m, llm: s } : m))).catch(() => {});
    }, 30000);
    return () => clearInterval(id);
  }, []);
  const recheckLlm = async () => {
    const s = await api.llm(true);
    setMeta((m) => (m ? { ...m, llm: s } : m));
  };
  const sc = meta?.scenarios.find((s) => s.id === scenario);
  const shownView = useMemo(() => {
    if (selCp === null || !view.checkpoints[selCp]) return view;
    return { ...view, values: view.checkpoints[selCp].values };
  }, [view, selCp]);
  const highlight = selCp !== null && view.checkpoints[selCp] ? view.stepTasks[view.checkpoints[selCp].step] : undefined;

  return (
    <div className="app">
      <header>
        <div className="brand">
          <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true"><path d="M2 16h5l3-9 5 18 4-14 3 5h8" fill="none" stroke="#dafa9c" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /></svg>
          <div>
            <div className="b1">Vibration Diagnosis Agents</div>
            <div className="b2">LangGraph multi-agent condition monitoring for rotating machinery</div>
          </div>
        </div>
        <div className="hdr-right">
          {modeSwitch}
          {view.status === "done" && view.threadId && (
            <button type="button" className="btn cm-report-btn" onClick={() => downloadReport(view.threadId!)}><Icon name="download" size={14} /> Report</button>
          )}
          {view.threadId && <span className={`run-pill st-${view.status}`}>{view.status === "running" && <i className="spin" />}{view.status} · {view.threadId}</span>}
          {meta && (
            <button type="button" className={`llm-pill ${meta.llm.available ? "on" : "off"}`} title={`${meta.llm.detail} (click to re-check)`} onClick={recheckLlm}>
              <span className="llm-dot" />
              {meta.llm.available ? `LLM live · ${meta.llm.model} via AvalAI` : `LLM offline (${meta.llm.detail}) · rule fallback`}
              <Icon name="refresh" size={13} />
            </button>
          )}
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <div className="sb-title">Run setup</div>
          <label>Asset</label>
          <div className="assets">
            {meta?.assets.map((a) => (
              <button type="button" key={a.id} className={`asset ${a.id === assetId ? "on" : ""}`} aria-pressed={a.id === assetId} onClick={() => setAssetId(a.id)}>
                <b>{a.id}</b> <span>{a.name.replace(a.id, "").trim()}</span>
                <small>{a.rpm} rpm · {a.power_kw} kW · {a.bearing.model} · ISO {a.iso_group.replace("group", "G")} {a.foundation}</small>
              </button>
            ))}
          </div>
          <label htmlFor="scenario">Fault scenario (simulated)</label>
          <select id="scenario" value={scenario} onChange={(e) => setScenario(e.target.value)}>
            {meta?.scenarios.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
          {sc && <div className="hint">{sc.blurb}</div>}
          <label>Severity</label>
          <div className="seg" role="group" aria-label="Severity">
            {meta?.levels.map((l) => <button type="button" key={l} aria-pressed={l === level} className={l === level ? "on" : ""} onClick={() => setLevel(l)}>{l}</button>)}
          </div>
          <label htmlFor="location">Measurement point</label>
          <select id="location" value={location} onChange={(e) => setLocation(e.target.value)}>
            {asset?.measurement_points.map((p) => <option key={p}>{p}</option>)}
          </select>
          <label className="row"><input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} /> Use LLM agents (falls back to rules if unreachable)</label>
          <label htmlFor="pace">Demo pace <span className="muted">{pace.toFixed(1)} s per DSP step</span></label>
          <input id="pace" type="range" min={0} max={2} step={0.1} value={pace} onChange={(e) => setPace(Number(e.target.value))} />
          <button className="btn primary big" onClick={start} disabled={!meta || view.status === "running"}>
            {view.status === "running" ? <><i className="spin" /> Agents working…</> : <><Icon name="play" size={14} /> Run diagnosis</>}
          </button>
          {err && <div className="error">{err}</div>}

          <div className="sb-title mt">Recent runs</div>
          <div className="runs">
            {runs.length === 0 && <div className="muted small">None yet.</div>}
            {runs.slice(0, 12).map((r) => (
              <button type="button" key={r.thread_id} className={`runrow ${r.thread_id === view.threadId ? "on" : ""}`} aria-current={r.thread_id === view.threadId} onClick={() => { setSelCp(null); attach(r.thread_id); }}>
                <span className={`dot st-${r.status}`} />
                <span>{r.asset_id} · {r.scenario}</span>
                <small>{r.status}</small>
              </button>
            ))}
          </div>
        </aside>

        <main>
          <section className="graph-card">
            <div className="sec-head">
              <span>Agent graph <span className="muted small">compiled StateGraph · live execution</span></span>
              {selCp !== null && <span className="tt-note"><Icon name="history" size={13} /> Time-travel: viewing checkpoint step {view.checkpoints[selCp]?.step}</span>}
            </div>
            <GraphView topo={topo} view={view} highlight={highlight} />
            <Timeline view={view} selected={selCp} onSelect={setSelCp} />
          </section>
          <section className="tabs-card">
            <div className="tabs" role="tablist" aria-label="Run results">
              {TABS.map((t) => (
                <button type="button" role="tab" aria-selected={t === tab} key={t} className={`tab ${t === tab ? "on" : ""}`} onClick={() => { setTab(t); setFollow(false); }}>
                  {t}{t === "Work order" && view.status === "interrupted" && <span className="badge amber">needs you</span>}
                </button>
              ))}
              <label className="follow"><input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> follow active agent</label>
            </div>
            {view.status === "idle" && !view.threadId ? (
              <div className="welcome">
                <h2>How to use this demo</h2>
                <ol>
                  <li>Pick an asset and a simulated fault on the left, then press <b>Run diagnosis</b>.</li>
                  <li>Watch the graph: the glowing edge is the last transition, counters show loops, and parallel branches light up together.</li>
                  <li>The timeline below the graph lists every super-step. Click one to time-travel the state inspector to that checkpoint.</li>
                  <li>For P1/P2 work orders the graph pauses at <code>interrupt()</code>. Approve, or reject with a comment to send it back to the planner.</li>
                </ol>
                <p className="muted">Try <b>Shaft misalignment</b> (confidence loop requests an axial reading), <b>Loose sensor</b> (QA rejects and re-acquires) and <b>Healthy</b> (fast path).</p>
              </div>
            ) : (
              <>
                {tab === "Signals" && <SignalsPanel view={shownView} />}
                {tab === "Diagnosis" && <DiagnosisPanel view={shownView} />}
                {tab === "Prognosis" && <PrognosisPanel view={shownView} />}
                {tab === "Work order" && <WorkOrderPanel view={shownView} onResume={resume} />}
                {tab === "Report" && <ReportPanel view={shownView} />}
              </>
            )}
          </section>
        </main>

        <aside className="rightbar">
          <div className="seg wide" role="group" aria-label="Side panel">
            <button type="button" aria-pressed={side === "activity"} className={side === "activity" ? "on" : ""} onClick={() => setSide("activity")}>Agent activity</button>
            <button type="button" aria-pressed={side === "state"} className={side === "state" ? "on" : ""} onClick={() => setSide("state")}>State inspector</button>
          </div>
          {side === "activity" ? <ActivityFeed view={view} /> : <StateInspector view={view} selected={selCp} />}
        </aside>
      </div>
      <ReportToast view={view} />
    </div>
  );
}
