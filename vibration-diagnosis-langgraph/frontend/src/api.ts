import type { Meta, SignalPreview, Topology } from "./types";

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export const api = {
  meta: () => fetch("/api/meta").then((r) => j<Meta>(r)),
  llm: (force = false) => fetch(`/api/llm?force=${force}`).then((r) => j<any>(r)),
  graph: () => fetch("/api/graph").then((r) => j<Topology>(r)),
  runs: () => fetch("/api/runs").then((r) => j<any[]>(r)),
  start: (body: object) =>
    fetch("/api/runs", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
      .then((r) => j<{ thread_id: string }>(r)),
  resume: (tid: string, body: object) =>
    fetch(`/api/runs/${tid}/resume`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })
      .then((r) => j<any>(r)),
  signal: (ref: string) => fetch(`/api/signals/${ref}`).then((r) => j<SignalPreview>(r)),
};
