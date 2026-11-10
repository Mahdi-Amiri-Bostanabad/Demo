import { useEffect, useRef, useState } from "react";
import type { RunView } from "../types";
import Icon from "./Icon";

export const reportUrl = (tid: string, inline = false) => `/api/runs/${tid}/report${inline ? "?inline=true" : ""}`;

export function downloadReport(tid: string) {
  const a = document.createElement("a");
  a.href = reportUrl(tid);
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/** When a run finishes live, download its report once and show a small card to get it again. */
export default function ReportToast({ view }: { view: RunView }) {
  const [shown, setShown] = useState<string | null>(null);
  const handled = useRef(new Set<string>());
  useEffect(() => {
    const tid = view.threadId;
    if (view.status !== "done" || !tid || handled.current.has(tid)) return;
    handled.current.add(tid);
    // a run replayed from a link or the run list finished long ago: offer the report, don't push a download
    const fresh = view.doneAt ? Date.now() - Date.parse(view.doneAt) < 30000 : false;
    let already = false;
    try { already = sessionStorage.getItem(`report-${tid}`) === "1"; sessionStorage.setItem(`report-${tid}`, "1"); } catch { /* ignore */ }
    if (fresh && !already) downloadReport(tid);
    setShown(tid);
  }, [view.status, view.threadId, view.doneAt]);
  useEffect(() => { if (shown && shown !== view.threadId) setShown(null); }, [view.threadId]);
  if (!shown || shown !== view.threadId) return null;
  return (
    <div className="report-toast" role="status">
      <Icon name="download" size={16} />
      <div className="rt-text"><b>Run report</b><small>graph, charts, results, work order, log · one HTML file</small></div>
      <a className="btn tiny-btn" href={reportUrl(shown, true)} target="_blank" rel="noreferrer"><Icon name="external" size={13} /> Open</a>
      <button type="button" className="btn primary tiny-btn" onClick={() => downloadReport(shown)}><Icon name="download" size={13} /> Download</button>
      <button type="button" className="rt-close" aria-label="Dismiss" onClick={() => setShown(null)}><Icon name="cross" size={14} /></button>
    </div>
  );
}
