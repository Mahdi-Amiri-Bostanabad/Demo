import { useEffect, useState } from "react";
import CommercialPage from "./pages/CommercialPage";
import DevPage from "./pages/DevPage";

// Two pages over the same backend and the same runs:
//   /commercial  minimal showcase (input, live graph, engineering diagrams)
//   /dev         full engineering view (state inspector, timeline, transcripts)
// The choice is remembered per browser; "/" opens the last one used (commercial the first time).
export type Mode = "commercial" | "dev";
const KEY = "vda-mode";

function modeFromPath(): Mode | null {
  const p = window.location.pathname.replace(/\/+$/, "");
  return p === "/commercial" ? "commercial" : p === "/dev" ? "dev" : null;
}
function remembered(): Mode {
  try {
    const s = localStorage.getItem(KEY);
    if (s === "commercial" || s === "dev") return s;
  } catch { /* storage blocked */ }
  return "commercial";
}

export function ModeSwitch({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  return (
    <div className="mode-switch" role="group" aria-label="Page mode">
      <button type="button" aria-pressed={mode === "commercial"} className={mode === "commercial" ? "on" : ""} onClick={() => onChange("commercial")}>Commercial</button>
      <button type="button" aria-pressed={mode === "dev"} className={mode === "dev" ? "on" : ""} onClick={() => onChange("dev")}>Dev</button>
    </div>
  );
}

export default function App() {
  const [mode, setMode] = useState<Mode>(() => modeFromPath() ?? remembered());

  useEffect(() => {
    // canonical URL: /<mode>?run=<id> keeps the run when switching or reloading
    if (modeFromPath() !== mode) history.replaceState(null, "", `/${mode}${window.location.search}`);
    try { localStorage.setItem(KEY, mode); } catch { /* ignore */ }
  }, [mode]);
  useEffect(() => {
    const onPop = () => setMode(modeFromPath() ?? remembered());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const change = (m: Mode) => {
    if (m === mode) return;
    history.pushState(null, "", `/${m}${window.location.search}`);
    setMode(m);
  };
  const sw = <ModeSwitch mode={mode} onChange={change} />;
  return mode === "commercial" ? <CommercialPage key="c" modeSwitch={sw} /> : <DevPage key="d" modeSwitch={sw} />;
}
