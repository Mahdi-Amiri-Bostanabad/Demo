import { useEffect, useRef, useState } from "react";
import { KIND_STYLE, NODE_META } from "../meta";
import type { RunView } from "../types";
import Icon from "./Icon";


export default function ActivityFeed({ view }: { view: RunView }) {
  const ref = useRef<HTMLDivElement>(null);
  const [hideProgress, setHideProgress] = useState(false);
  const items = hideProgress ? view.feed.filter((f) => f.kind !== "progress") : view.feed;
  const live = Object.entries(view.tokens).filter(([n, t]) => t && view.nodeStatus[n] === "active");
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [items.length, live.map(([, t]) => t.length).join()]);
  return (
    <div className="feed-wrap">
      <label className="small muted feed-opt"><input type="checkbox" checked={hideProgress} onChange={(e) => setHideProgress(e.target.checked)} /> hide progress pings</label>
      <div className="feed" ref={ref} aria-live="polite">
        {items.length === 0 && <div className="empty">Agent messages, tool calls and routing decisions stream here.</div>}
        {items.map((f, i) => {
          const m = NODE_META[f.agent];
          const color = m ? KIND_STYLE[m.kind].color : "#a3a3a3";
          return (
            <div key={i} className={`fi fi-${f.kind}`}>
              <span className="fi-icon" style={{ color }}><Icon name={f.kind} size={13} /></span>
              <div>
                <div className="fi-head"><b style={{ color }}>{m?.label ?? f.agent}</b><span className="muted small">{f.ts?.slice(11, 19)}</span></div>
                <div className="fi-text">{f.text}</div>
              </div>
            </div>
          );
        })}
        {live.map(([n, t]) => (
          <div key={n} className="fi fi-llm streaming">
            <span className="fi-icon" style={{ color: KIND_STYLE.llm.color }}><Icon name="llm" size={13} /></span>
            <div>
              <div className="fi-head"><b style={{ color: KIND_STYLE.llm.color }}>{NODE_META[n]?.label ?? n}</b><span className="muted small">streaming tokens</span></div>
              <div className="fi-text">{t}<span className="caret" /></div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
