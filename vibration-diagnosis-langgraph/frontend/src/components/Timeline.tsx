import { useEffect, useRef } from "react";
import { KIND_STYLE, NODE_META } from "../meta";
import type { RunView } from "../types";

export default function Timeline({ view, selected, onSelect }: { view: RunView; selected: number | null; onSelect: (i: number | null) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (selected === null && ref.current) ref.current.scrollLeft = ref.current.scrollWidth;
  }, [view.checkpoints.length, selected]);
  return (
    <div className="timeline">
      <div className="tl-title">
        <span>Super-steps &amp; checkpoints</span>
        <span className="muted small">click a step to time-travel the state inspector</span>
        <button type="button" className={`btn tiny ${selected === null ? "on" : ""}`} aria-pressed={selected === null} onClick={() => onSelect(null)}><span className="live-dot" />Live</button>
      </div>
      <div className="tl-track" ref={ref}>
        {view.checkpoints.length === 0 && <span className="muted small">No checkpoints yet.</span>}
        {view.checkpoints.map((cp, i) => {
          const tasks = view.stepTasks[cp.step] || [];
          const active = (selected ?? view.checkpoints.length - 1) === i;
          return (
            <button type="button" key={cp.checkpoint_id + i} aria-pressed={active} className={`tl-chip ${active ? "active" : ""} ${tasks.length > 1 && cp.step > 0 ? "parallel" : ""}`} onClick={() => onSelect(i)}
              title={`checkpoint ${cp.checkpoint_id}\nnext: ${cp.next.join(", ") || "END"}`}>
              <div className="tl-step">{cp.step < 0 ? "in" : cp.step}</div>
              <div className="tl-nodes">
                {(cp.step <= 0 ? [cp.step < 0 ? "input" : "__start__"] : tasks).map((t) => (
                  <span key={t} style={{ ["--kc" as any]: NODE_META[t] ? KIND_STYLE[NODE_META[t].kind].color : "#737373" }}>
                    {NODE_META[t]?.label ?? t}
                  </span>
                ))}
              </div>
              {tasks.length > 1 && cp.step > 0 && <div className="tl-par">parallel</div>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
