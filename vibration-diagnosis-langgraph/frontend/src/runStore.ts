import { useCallback, useEffect, useReducer, useRef } from "react";
import type { Ev, RunView, Topology } from "./types";

export const emptyRun = (): RunView => ({
  threadId: null, status: "idle", checkpoints: [], stepTasks: { 0: ["__start__"] }, nodeStatus: {}, visits: {},
  edgeCounts: {}, lastEdges: [], values: {}, lastWriter: {}, interrupt: null, progress: {}, tokens: {}, feed: [],
  curStep: 0,
});

type Action = { type: "reset"; threadId: string | null } | { type: "event"; ev: Ev; topo: Topology | null };

function applyEvent(s: RunView, ev: Ev, topo: Topology | null): RunView {
  const n: RunView = { ...s };
  switch (ev.kind) {
    case "run_started":
      n.meta = ev.meta;
      n.nodeStatus = { __start__: "done" };
      break;
    case "status":
      n.status = ev.status;
      if (ev.status === "error") n.error = ev.error;
      if (ev.status === "done") {
        n.doneAt = ev.ts;
        n.nodeStatus = { ...n.nodeStatus, __end__: "done" };
        const k = "report->__end__";
        n.edgeCounts = { ...n.edgeCounts, [k]: (n.edgeCounts[k] || 0) + 1 };
        n.lastEdges = [k];
        n.feed = [...n.feed, { seq: ev.seq, ts: ev.ts, agent: "system", kind: "status", text: "Run completed." }];
      }
      if (ev.status === "interrupted") {
        n.interrupt = ev.interrupts?.[0]?.value ?? n.interrupt;
        n.feed = [...n.feed, { seq: ev.seq, ts: ev.ts, agent: "human_review", kind: "human",
          text: "Graph paused by interrupt(). Waiting for engineer approval." }];
      }
      if (ev.status === "error")
        n.feed = [...n.feed, { seq: ev.seq, ts: ev.ts, agent: "system", kind: "warn", text: `Run failed: ${ev.error}` }];
      break;
    case "checkpoint": {
      n.checkpoints = [...n.checkpoints, { checkpoint_id: ev.checkpoint_id, step: ev.step, next: ev.next, values: ev.values, source: ev.source, seq: ev.seq }];
      n.values = ev.values;
      n.curStep = (ev.step ?? -1) + 1;
      break;
    }
    case "task_start": {
      const node = ev.node as string;
      const step = n.curStep;
      const prev = n.stepTasks[step - 1] || [];
      n.stepTasks = { ...n.stepTasks, [step]: Array.from(new Set([...(n.stepTasks[step] || []), node])) };
      n.nodeStatus = { ...n.nodeStatus, [node]: "active" };
      n.visits = { ...n.visits, [node]: (n.visits[node] || 0) + 1 };
      const taken: string[] = [];
      for (const p of prev) {
        if (topo?.edges.some((e) => e.source === p && e.target === node)) taken.push(`${p}->${node}`);
      }
      if (taken.length) {
        const ec = { ...n.edgeCounts };
        taken.forEach((k) => (ec[k] = (ec[k] || 0) + 1));
        n.edgeCounts = ec;
        // parallel tasks in the same step share the "last edges" highlight
        const sameStep = n.lastEdges.filter((k) => (n.stepTasks[step] || []).includes(k.split("->")[1]));
        n.lastEdges = [...sameStep, ...taken];
      }
      n.tokens = { ...n.tokens, [node]: "" };
      n.progress = { ...n.progress, [node]: "" };
      if (node === "human_review" && n.interrupt && n.status !== "interrupted") n.interrupt = null;
      break;
    }
    case "task_end": {
      const st = ev.error ? "error" : ev.interrupted ? "interrupted" : "done";
      n.nodeStatus = { ...n.nodeStatus, [ev.node]: st };
      break;
    }
    case "update": {
      const upd = ev.update || {};
      const lw = { ...n.lastWriter };
      Object.keys(upd).forEach((k) => (lw[k] = { node: ev.node, step: n.curStep }));
      n.lastWriter = lw;
      const logs = (upd.agent_log || []) as any[];
      if (logs.length)
        n.feed = [...n.feed, ...logs.map((l) => ({ seq: ev.seq, ts: l.ts, agent: l.agent, kind: l.kind, text: l.text }))];
      if (ev.node === "diag_tools" && Array.isArray(upd.messages)) {
        n.feed = [...n.feed, ...upd.messages.map((m: any) => ({
          seq: ev.seq, ts: ev.ts, agent: "diag_tools", kind: "tool",
          text: `${m.name ?? "tool"} → ${String(m.content).slice(0, 220)}`,
        }))];
      }
      break;
    }
    case "progress":
      n.progress = { ...n.progress, [ev.agent]: ev.text };
      n.feed = [...n.feed, { seq: ev.seq, ts: ev.ts, agent: ev.agent, kind: "progress", text: ev.text }];
      break;
    case "token":
      if (ev.node) n.tokens = { ...n.tokens, [ev.node]: (n.tokens[ev.node] || "") + (ev.text || "") };
      break;
    case "interrupt":
      n.interrupt = ev.interrupts?.[0]?.value ?? null;
      break;
    case "resume":
      n.interrupt = null;
      n.feed = [...n.feed, { seq: ev.seq, ts: ev.ts, agent: "human_review", kind: "human",
        text: `Command(resume=…) sent: ${ev.decision}${ev.comment ? ` – "${ev.comment}"` : ""}` }];
      break;
  }
  return n;
}

function reducer(s: RunView, a: Action): RunView {
  if (a.type === "reset") return { ...emptyRun(), threadId: a.threadId, status: a.threadId ? "running" : "idle" };
  return applyEvent(s, a.ev, a.topo);
}

export function useRun(topo: Topology | null) {
  const [view, dispatch] = useReducer(reducer, undefined, emptyRun);
  const esRef = useRef<EventSource | null>(null);
  const topoRef = useRef(topo);
  topoRef.current = topo;

  const attach = useCallback((tid: string | null) => {
    esRef.current?.close();
    dispatch({ type: "reset", threadId: tid });
    if (!tid) return;
    const es = new EventSource(`/api/runs/${tid}/events?since=0`);
    let lastSeq = -1;
    es.onmessage = (m) => {
      const ev = JSON.parse(m.data) as Ev;
      if (ev.seq <= lastSeq) return; // de-dupe after auto-reconnect
      lastSeq = ev.seq;
      dispatch({ type: "event", ev, topo: topoRef.current });
    };
    es.onerror = () => {
      // EventSource reconnects by itself; on reconnect the server replays from 0 and we skip seen seqs.
    };
    esRef.current = es;
  }, []);

  useEffect(() => () => esRef.current?.close(), []);
  return { view, attach };
}
