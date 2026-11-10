"""Self-contained HTML run report: agent graph, engineering charts, results, work order, audit log.

One file, no external assets (inline CSS + SVG), light theme, print-ready (Print -> Save as PDF).
Built from the run's final state, its event stream (for the execution path) and SIGNAL_STORE previews.
"""
from __future__ import annotations

import html
import math
from datetime import datetime, timezone

from . import signals as S

E = html.escape

# Same layout as the UI graph (frontend/src/meta.ts) so the picture matches what people saw.
NODES = {
    "__start__": ("START", "terminal", 0, 22), "acquisition": ("Data Acquisition", "dsp", 100, 0),
    "signal_qa": ("Signal Quality", "dsp", 290, 0), "severity": ("ISO 20816 Severity", "dsp", 480, -85),
    "spectral": ("Spectral Analysis", "dsp", 480, 85), "triage": ("Supervisor: Triage", "supervisor", 670, 0),
    "diagnostician": ("Diagnostician", "llm", 860, 0), "diag_tools": ("Engineering Toolbox", "tool", 860, -165),
    "confidence_gate": ("Supervisor: Confidence", "supervisor", 1050, 0), "prognosis": ("Prognosis / RUL", "dsp", 1050, 270),
    "planner": ("Maintenance Planner", "llm", 860, 270), "human_review": ("Engineer Approval", "human", 670, 270),
    "report": ("Report", "output", 290, 270), "__end__": ("END", "terminal", 110, 292),
}
KIND = {"dsp": ("#0e7490", "DSP agent"), "supervisor": ("#52525b", "Router"), "llm": ("#be185d", "LLM agent"),
        "tool": ("#b45309", "Tools"), "human": ("#c2410c", "Human"), "output": ("#047857", "Output"), "terminal": ("#71717a", "")}
HANDLES = {
    "signal_qa->acquisition": ("t", "t"), "signal_qa->report": ("b", "t"), "triage->report": ("b", "r"),
    "diagnostician->diag_tools": ("t", "b"), "diag_tools->diagnostician": ("r", "r"), "confidence_gate->acquisition": ("t", "t"),
    "confidence_gate->prognosis": ("b", "t"), "confidence_gate->report": ("b", "r"), "prognosis->planner": ("l", "r"),
    "planner->human_review": ("l", "r"), "planner->report": ("b", "b"), "human_review->planner": ("b", "b"),
    "human_review->report": ("l", "r"), "report->__end__": ("l", "r"),
}
ZONE_C = {"A": "#16a34a", "B": "#65a30d", "C": "#d97706", "D": "#dc2626"}
FAULT = {"healthy": "Healthy", "unbalance": "Rotor unbalance", "misalignment": "Shaft misalignment",
         "looseness": "Mechanical looseness", "outer_race": "Bearing outer race defect", "inner_race": "Bearing inner race defect"}


# ------------------------------------------------------------------ execution path from the event stream

def execution(events: list[dict], topo: dict) -> tuple[dict[int, list[str]], dict[str, int], dict[str, int]]:
    steps: dict[int, list[str]] = {0: ["__start__"]}
    visits: dict[str, int] = {}
    edges: dict[str, int] = {}
    edge_set = {(e["source"], e["target"]) for e in topo["edges"]}
    cur = 0
    for ev in events:
        if ev["kind"] == "checkpoint":
            cur = (ev.get("step") if ev.get("step") is not None else -1) + 1
        elif ev["kind"] == "task_start":
            n = ev["node"]
            for p in steps.get(cur - 1, []):
                if (p, n) in edge_set:
                    edges[f"{p}->{n}"] = edges.get(f"{p}->{n}", 0) + 1
            steps.setdefault(cur, [])
            if n not in steps[cur]:
                steps[cur].append(n)
            visits[n] = visits.get(n, 0) + 1
        elif ev["kind"] == "status" and ev.get("status") == "done":
            edges["report->__end__"] = 1
            visits["__end__"] = 1
    visits["__start__"] = 1
    return steps, visits, edges


# ------------------------------------------------------------------ SVG helpers

def _ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    if hi <= lo:
        hi = lo + 1
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=raw)
    t = math.ceil(lo / step) * step
    out = []
    while t <= hi + 1e-9:
        out.append(round(t, 10))
        t += step
    return out


def _fmt(v: float) -> str:
    if v == 0:
        return "0"
    a = abs(v)
    return f"{v:.0f}" if a >= 10 else f"{v:.1f}" if a >= 1 else f"{v:.2g}"


def line_chart(series, xlim, ylim, w=760, h=230, vlines=(), hlines=(), bands=(), xlabel="", ylabel="") -> str:
    L, R, T, B = 52, 14, 18, 34
    pw, ph = w - L - R, h - T - B
    x0, x1 = xlim
    y0, y1 = ylim
    X = lambda x: L + (x - x0) / (x1 - x0) * pw
    Y = lambda y: T + ph - (min(max(y, y0), y1) - y0) / (y1 - y0) * ph
    o = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img">']
    for (b0, b1, c) in bands:
        o.append(f'<rect x="{L}" y="{Y(b1):.1f}" width="{pw}" height="{Y(b0) - Y(b1):.1f}" fill="{c}" fill-opacity=".09"/>')
    for t in _ticks(y0, y1):
        o.append(f'<line x1="{L}" x2="{L + pw}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" class="grid"/>'
                 f'<text x="{L - 6}" y="{Y(t) + 3.5:.1f}" text-anchor="end" class="tick">{_fmt(t)}</text>')
    for t in _ticks(x0, x1, 8):
        o.append(f'<text x="{X(t):.1f}" y="{T + ph + 14}" text-anchor="middle" class="tick">{_fmt(t)}</text>')
    o.append(f'<line x1="{L}" x2="{L + pw}" y1="{T + ph}" y2="{T + ph}" class="axis"/>')
    for (y, label, c) in hlines:
        o.append(f'<line x1="{L}" x2="{L + pw}" y1="{Y(y):.1f}" y2="{Y(y):.1f}" stroke="{c}" stroke-dasharray="4 3"/>'
                 f'<text x="{L + 4}" y="{Y(y) - 4:.1f}" class="lbl" fill="{c}">{E(label)}</text>')
    for (x, label, c) in vlines:
        if x0 <= x <= x1:
            o.append(f'<line x1="{X(x):.1f}" x2="{X(x):.1f}" y1="{T}" y2="{T + ph}" stroke="{c}" stroke-dasharray="3 3" stroke-opacity=".8"/>'
                     f'<text x="{X(x):.1f}" y="{T - 5}" text-anchor="middle" class="lbl" fill="{c}">{E(label)}</text>')
    o.append(f'<clipPath id="c{id(series)}"><rect x="{L}" y="{T}" width="{pw}" height="{ph}"/></clipPath><g clip-path="url(#c{id(series)})">')
    for (xs, ys, c, dash, sw) in series:
        pts = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in zip(xs, ys) if x0 <= x <= x1)
        o.append(f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="{sw}"{f" stroke-dasharray={chr(34)}{dash}{chr(34)}" if dash else ""}/>')
    o.append("</g>")
    if xlabel:
        o.append(f'<text x="{L + pw}" y="{h - 3}" text-anchor="end" class="axlbl">{E(xlabel)}</text>')
    if ylabel:
        o.append(f'<text x="12" y="{T + ph / 2}" transform="rotate(-90 12 {T + ph / 2})" text-anchor="middle" class="axlbl">{E(ylabel)}</text>')
    o.append("</svg>")
    return "".join(o)


def graph_svg(topo: dict, visits: dict, edges: dict) -> str:
    W, H = 158, 74
    ox, oy = 20, 200

    def box(n):
        _, kind, x, y = NODES[n]
        if kind == "terminal":
            return x + ox, y + oy, 70, 30
        return x + ox, y + oy, W, H

    def pt(n, side):
        x, y, w, h = box(n)
        return {"t": (x + w / 2, y), "b": (x + w / 2, y + h), "l": (x, y + h / 2), "r": (x + w, y + h / 2)}[side]

    def path(s, t):
        ss, ts = HANDLES.get(f"{s}->{t}", ("r", "l"))
        (sx, sy), (tx, ty) = pt(s, ss), pt(t, ts)
        if ss in "lr" and ts in "lr":
            if ss == ts:
                xx = (max(sx, tx) + 28) if ss == "r" else (min(sx, tx) - 28)
                return f"M{sx},{sy} H{xx} V{ty} H{tx}"
            mx = (sx + tx) / 2
            return f"M{sx},{sy} H{mx} V{ty} H{tx}"
        if ss in "tb" and ts in "tb":
            if ss == ts:
                yy = (min(sy, ty) - 28) if ss == "t" else (max(sy, ty) + 28)
                return f"M{sx},{sy} V{yy} H{tx} V{ty}"
            my = (sy + ty) / 2
            return f"M{sx},{sy} V{my} H{tx} V{ty}"
        return f"M{sx},{sy} V{ty} H{tx}"

    o = ['<svg viewBox="0 0 1250 520" class="graph" role="img" aria-label="Agent graph with the executed path">',
         '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
         '<path d="M0 0L10 5L0 10z" fill="#a1a1aa"/></marker>'
         '<marker id="ahh" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
         '<path d="M0 0L10 5L0 10z" fill="#4d7c0f"/></marker></defs>']
    for e in topo["edges"]:
        k = f"{e['source']}->{e['target']}"
        if e["source"] not in NODES or e["target"] not in NODES:
            continue
        c = edges.get(k, 0)
        st = 'stroke="#4d7c0f" stroke-width="2.2" marker-end="url(#ahh)"' if c else \
             f'stroke="#d4d4d8" stroke-width="1.2" marker-end="url(#ah)"{" stroke-dasharray=" + chr(34) + "5 4" + chr(34) if e["conditional"] else ""}'
        o.append(f'<path d="{path(e["source"], e["target"])}" fill="none" {st}/>')
        if c > 1:
            (sx, sy) = pt(e["target"], HANDLES.get(k, ("r", "l"))[1])
            o.append(f'<text x="{sx - 4}" y="{sy - 6}" text-anchor="end" class="ecount">×{c}</text>')
    for n, (label, kind, x, y) in NODES.items():
        bx, by, bw, bh = box(n)
        col, tag = KIND[kind]
        ran = visits.get(n, 0) > 0
        fill = "#f7fee7" if ran else "#ffffff"
        stroke = col if ran else "#d4d4d8"
        if kind == "terminal":
            o.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="15" fill="{fill}" stroke="{stroke}"/>'
                     f'<text x="{bx + bw / 2}" y="{by + 19}" text-anchor="middle" class="nterm">{label}</text>')
            continue
        o.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="{1.8 if ran else 1}"/>'
                 f'<rect x="{bx}" y="{by + 10}" width="3" height="{bh - 20}" fill="{col}"/>'
                 f'<text x="{bx + 12}" y="{by + 20}" class="ntag" fill="{col}">{tag.upper()}</text>'
                 f'<text x="{bx + 12}" y="{by + 40}" class="nlabel">{E(label)}</text>')
        if visits.get(n):
            o.append(f'<text x="{bx + bw - 10}" y="{by + 20}" text-anchor="end" class="nvis">×{visits[n]}</text>')
        else:
            o.append(f'<text x="{bx + 12}" y="{by + 60}" class="nskip">not executed</text>')
    o.append("</svg>")
    return "".join(o)


def zone_svg(sev: dict) -> str:
    ab, bc, cd = sev["limits"]["A/B"], sev["limits"]["B/C"], sev["limits"]["C/D"]
    mx = cd * 1.5
    X = lambda v: 20 + min(1.0, v / mx) * 600
    o = ['<svg viewBox="0 0 640 96" class="chart narrow" role="img">']
    for z, a, b in (("A", 0, ab), ("B", ab, bc), ("C", bc, cd), ("D", cd, mx)):
        op = 1 if z == sev["zone"] else 0.25
        o.append(f'<rect x="{X(a):.1f}" y="30" width="{X(b) - X(a) - 2:.1f}" height="26" rx="4" fill="{ZONE_C[z]}" fill-opacity="{op}"/>'
                 f'<text x="{(X(a) + X(b)) / 2:.1f}" y="48" text-anchor="middle" class="zlbl">{z}</text>')
    for l in (ab, bc, cd):
        o.append(f'<text x="{X(l):.1f}" y="74" text-anchor="middle" class="tick">{l}</text>')
    v = sev["velocity_rms_mm_s"]
    o.append(f'<line x1="{X(v):.1f}" x2="{X(v):.1f}" y1="22" y2="62" stroke="#18181b" stroke-width="2.5"/>'
             f'<text x="{X(v):.1f}" y="16" text-anchor="middle" class="lbl" fill="#18181b">{v} mm/s</text>'
             f'<text x="620" y="92" text-anchor="end" class="axlbl">velocity RMS, mm/s (10–1000 Hz) · {E(sev["standard"])}</text></svg>')
    return "".join(o)


def bars_svg(hyps: list[dict]) -> str:
    o = [f'<svg viewBox="0 0 640 {len(hyps) * 26 + 6}" class="chart narrow" role="img">']
    for i, h in enumerate(hyps):
        y = 4 + i * 26
        o.append(f'<text x="150" y="{y + 14}" text-anchor="end" class="blbl">{E(FAULT.get(h["fault"], h["fault"]))}</text>'
                 f'<rect x="160" y="{y + 3}" width="420" height="14" rx="3" fill="#f4f4f5"/>'
                 f'<rect x="160" y="{y + 3}" width="{420 * h["score"]:.1f}" height="14" rx="3" fill="#65a30d"/>'
                 f'<text x="590" y="{y + 14}" class="blbl">{h["score"]:.2f}</text>')
    o.append("</svg>")
    return "".join(o)


# ------------------------------------------------------------------ HTML

CSS = """
*{box-sizing:border-box} body{margin:0;background:#f4f4f5;color:#18181b;font:14px/1.5 "Segoe UI",system-ui,-apple-system,sans-serif}
.page{max-width:1080px;margin:0 auto;padding:32px 28px 60px;background:#fff}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.02em} h2{font-size:18px;margin:34px 0 10px;padding-top:14px;border-top:1px solid #e4e4e7}
h3{font-size:14px;margin:18px 0 6px;color:#3f3f46}
.meta{color:#71717a;font-size:12.5px} .head{display:flex;justify-content:space-between;gap:20px;align-items:flex-start}
.badge{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.06em}
.st-action_required{background:#ffedd5;color:#9a3412}.st-healthy{background:#dcfce7;color:#166534}.st-on_hold,.st-inconclusive{background:#ede9fe;color:#5b21b6}
.headline{font-size:16px;font-weight:600;margin:12px 0 0;padding:12px 14px;border-left:4px solid #65a30d;background:#f7fee7}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:16px}
.kpi{border:1px solid #e4e4e7;border-radius:10px;padding:10px 12px}.kpi i{display:block;font-style:normal;font-size:11px;color:#71717a;text-transform:uppercase;letter-spacing:.08em}
.kpi b{font-size:19px;display:block;font-variant-numeric:tabular-nums}.kpi small{color:#52525b}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin:6px 0}th{text-align:left;color:#71717a;font-weight:600;font-size:11.5px}
th,td{padding:5px 8px;border-bottom:1px solid #e4e4e7;vertical-align:top}td.num{font-variant-numeric:tabular-nums;white-space:nowrap}
.ok{color:#15803d;font-weight:600}.bad{color:#b91c1c;font-weight:600}
.chart,.graph{width:100%;height:auto;display:block;margin:4px 0 8px}.chart.narrow{max-width:680px}
.grid{stroke:#f0f0f1}.axis{stroke:#a1a1aa}.tick{fill:#71717a;font-size:10.5px}.lbl{font-size:10.5px;font-weight:600}.axlbl{fill:#71717a;font-size:10.5px}
.zlbl{fill:#fff;font-size:12px;font-weight:700}.blbl{fill:#27272a;font-size:12px}
.ntag{font-size:9.5px;font-weight:700;letter-spacing:.08em}.nlabel{font-size:13px;font-weight:600;fill:#18181b}.nvis{font-size:11px;fill:#4d7c0f;font-weight:700}
.nskip{font-size:10.5px;fill:#a1a1aa}.nterm{font-size:11px;font-weight:700;fill:#52525b}.ecount{font-size:10.5px;fill:#4d7c0f;font-weight:700}
.steps{display:flex;flex-wrap:wrap;gap:5px;margin:8px 0}.steps span{font-size:11.5px;border:1px solid #d4d4d8;border-radius:6px;padding:2px 7px;background:#fafafa}
.steps span.par{border-color:#65a30d;background:#f7fee7}
ul.ev{margin:4px 0 8px;padding-left:20px} .tool{font-family:Consolas,monospace;font-size:11.5px;color:#9d174d}
.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}.note{font-size:12.5px;padding:8px 12px;border-radius:8px;background:#f4f4f5;margin:8px 0}
.note.warn{background:#fef3c7}.note.ok{background:#dcfce7}.prio{font-weight:800}.k-decision{font-weight:600}.k-warn{color:#b45309}.k-human{color:#c2410c}
.legend{display:flex;gap:14px;font-size:11.5px;color:#52525b;flex-wrap:wrap}.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
footer{margin-top:40px;color:#a1a1aa;font-size:11.5px;border-top:1px solid #e4e4e7;padding-top:10px}
@media print{body{background:#fff}.page{padding:0;max-width:none}h2{break-before:auto;break-after:avoid}.chart,.graph,table,.kpis{break-inside:avoid}}
"""


def build_report(run, values: dict, topo: dict) -> str:
    v = values
    a = v.get("asset", {})
    rep = v.get("report", {})
    sev, d, p, wo, rv = v.get("severity"), v.get("diagnosis"), v.get("prognosis"), v.get("work_order"), v.get("review")
    ms = v.get("measurements", [])
    rej = set(v.get("rejected", []))
    steps, visits, edges = execution(run.events, topo)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    o = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>Vibration report {E(a.get('id', ''))} {E(run.thread_id)}</title><style>{CSS}</style></head><body><div class='page'>"]

    # header
    o.append(f"<div class='head'><div><h1>Vibration Diagnosis Report</h1><div class='meta'>{E(a.get('name', ''))} · {E(a.get('site', ''))}<br>"
             f"Run {E(run.thread_id)} · started {E(run.meta.get('started_at', '')[:19].replace('T', ' '))} UTC · generated {now}</div></div>"
             f"<span class='badge st-{E(rep.get('status', ''))}'>{E(rep.get('status', '').replace('_', ' '))}</span></div>"
             f"<div class='headline'>{E(rep.get('headline', ''))}</div>")
    kp = []
    kp.append(("Diagnosis", FAULT.get(d["primary_fault"], d["fault_title"]) if d else "Healthy",
               f"confidence {round(d['confidence'] * 100)}% · {d['mode']}" if d else "fast path, no fault rule fired"))
    if sev:
        kp.append(("ISO 20816 severity", f"Zone {sev['zone']}", f"{sev['velocity_rms_mm_s']} mm/s RMS"))
    if p:
        kp.append(("Remaining useful life", "no growth" if p["rul_days"] is None else f"{p['rul_days']} days",
                   f"band {p['rul_range'][0]}–{p['rul_range'][1]} d"))
    if wo:
        kp.append(("Work order", f"{wo['id']} · {wo['priority']}",
                   f"due ≤ {wo['due_within_days']} d · " + (f"{rv['decision']}d by {E(rv['reviewer'])}" if rv else
                                                          "auto-approved" if not wo["requires_approval"] else "pending")))
    o.append("<div class='kpis'>" + "".join(f"<div class='kpi'><i>{E(t)}</i><b>{E(b)}</b><small>{c}</small></div>" for t, b, c in kp) + "</div>")

    # graph
    o.append("<h2>1. Agent workflow (LangGraph)</h2><p class='meta'>The compiled StateGraph. Green edges were traversed in this run "
             "(×n = times), filled nodes executed (×n = visits), grey dashed edges are conditional routes not taken.</p>")
    o.append(graph_svg(topo, visits, edges))
    o.append("<div class='legend'>" + "".join(f"<span><i style='background:{c}'></i>{t}</span>" for k, (c, t) in KIND.items() if t) + "</div>")
    o.append("<h3>Execution path by super-step</h3><div class='steps'>")
    for s in sorted(steps):
        ns = steps[s]
        o.append(f"<span class='{'par' if len(ns) > 1 else ''}'>{s} · {' ∥ '.join(E(NODES.get(n, (n,))[0]) for n in ns)}</span>")
    o.append(f"<span>END</span></div><p class='meta'>{sum(1 for e in run.events if e['kind'] == 'checkpoint')} checkpoints written · "
             f"LLM usage: {E(', '.join(f'{k} {m}' for k, m in (v.get('llm_usage') or {}).items()) or 'none (fast path)')}</p>")

    # asset + measurements
    if a:
        b = a["bearing"]
        o.append("<h2>2. Machine and measurements</h2><div class='two'><table>"
                 + "".join(f"<tr><th>{k}</th><td>{E(str(val))}</td></tr>" for k, val in [
                     ("Asset", f"{a['id']} {a['name']}"), ("Type", a["type"]), ("Speed", f"{a['rpm']} rpm ({a['rpm'] / 60:.2f} Hz)"),
                     ("Power", f"{a['power_kw']} kW"), ("Bearing", f"{b['model']} · {b['n_balls']} balls · d {b['ball_d_mm']} / D {b['pitch_d_mm']} mm"),
                     ("ISO class", f"{a['iso_group'].replace('group', 'Group ')}, {a['foundation']} foundation"), ("Criticality", a["criticality"])])
                 + "</table><table>")
        bf = (v.get("spectral") or {}).get("radial", {}).get("bearing_freqs_hz")
        if bf:
            o.append("".join(f"<tr><th>{k}</th><td class='num'>{bf[k]} Hz</td></tr>" for k in ("shaft_hz", "FTF", "BSF", "BPFO", "BPFI")))
        o.append("</table></div>")
    if ms:
        o.append("<table><tr><th>ID</th><th>Point</th><th>Direction</th><th>Purpose</th><th>v RMS mm/s</th><th>Kurtosis</th><th>Crest</th><th>QA</th></tr>")
        for m in ms:
            f = m["features"]
            o.append(f"<tr><td>{m['id']}</td><td>{E(m['location'])}</td><td>{m['direction']}</td><td>{E(m['purpose'])}</td>"
                     f"<td class='num'>{f['velocity_rms_mm_s']}</td><td class='num'>{f['kurtosis']}</td><td class='num'>{f['crest_factor']}</td>"
                     f"<td class='{'bad' if m['id'] in rej else 'ok'}'>{'rejected' if m['id'] in rej else 'pass'}</td></tr>")
        o.append("</table>")

    # signals
    valid = [m for m in ms if m["id"] not in rej and m["signal_ref"] in S.SIGNAL_STORE]
    if valid:
        o.append("<h2>3. Signal analysis</h2>")
        fr = a["rpm"] / 60
        bf = (v.get("spectral") or {}).get("radial", {}).get("bearing_freqs_hz") or {}
        for m in valid:
            pv = S.previews(m["signal_ref"])
            o.append(f"<h3>{m['id']} · {E(m['location'])} {m['direction']} — time waveform (acceleration, g)</h3>")
            wf = pv["waveform"]
            ymax = max(abs(min(wf["g"])), abs(max(wf["g"]))) * 1.1 or 1
            o.append(line_chart([(wf["t_ms"], wf["g"], "#0e7490", "", 1)], (0, max(wf["t_ms"])), (-ymax, ymax), h=180, xlabel="time, ms", ylabel="g"))
            sp = pv["spectrum"]
            xmax = min(1000, math.ceil(fr * 12))
            ys = [y for x, y in zip(sp["f"], sp["v"]) if x <= xmax]
            o.append(f"<h3>{m['id']} — velocity spectrum (mm/s peak), orders of running speed marked</h3>")
            o.append(line_chart([(sp["f"], sp["v"], "#4d7c0f", "", 1.2)], (0, xmax), (0, max(ys) * 1.15 or 1),
                                vlines=[(h * fr, f"{h:g}X", "#7c3aed") for h in (0.5, 1, 2, 3, 4, 5, 6, 8, 10)], xlabel="frequency, Hz", ylabel="mm/s"))
            if m["direction"] != "Axial":
                ev = pv["envelope"]
                o.append(f"<h3>{m['id']} — envelope spectrum (2–5 kHz demodulated, g), bearing defect frequencies marked</h3>")
                vl = [(bf[k] * h, f"{k}" if h == 1 else f"{h}×", c) for k, c in (("BPFO", "#be185d"), ("BPFI", "#b45309")) for h in (1, 2, 3) if bf.get(k)]
                vl += [(bf[k], k, "#71717a") for k in ("BSF", "FTF") if bf.get(k)]
                o.append(line_chart([(ev["f"], ev["a"], "#047857", "", 1.2)], (0, 400), (0, max(ev["a"]) * 1.15 or 1),
                                    vlines=vl, xlabel="frequency, Hz", ylabel="g"))

    # diagnosis
    if sev:
        o.append("<h2>4. Severity and diagnosis</h2><h3>ISO 20816 severity zone</h3>" + zone_svg(sev)
                 + f"<p class='meta'>{E(sev['zone_text'])}. Governed by {sev['governing_measurement']}.</p>")
    if v.get("hypotheses"):
        o.append("<h3>Rule-engine prior (spectral agent)</h3>" + bars_svg(v["hypotheses"]))
    if v.get("triage"):
        o.append(f"<div class='note'>Supervisor: {E(v['triage']['reason'])}</div>")
    if d:
        o.append(f"<h3>Diagnosis: {E(d['fault_title'])} — confidence {round(d['confidence'] * 100)}% ({E(d['mode'])}, round {d['round']})</h3>"
                 "<ul class='ev'>" + "".join(f"<li>{E(x)}</li>" for x in d["evidence"]) + "</ul>"
                 + (f"<p>{E(d['rationale'])}</p>" if d.get("rationale") else ""))
    msgs = v.get("messages") or []
    calls = [(t["name"], t["args"]) for m in msgs if m.get("type") == "ai" for t in m.get("tool_calls", [])]
    if calls:
        o.append("<h3>LLM tool calls</h3><ol>" + "".join(
            f"<li><span class='tool'>{E(n)}({E(', '.join(f'{k}={val}' for k, val in args.items() if k not in ('evidence', 'rationale')))[:180]})</span></li>"
            for n, args in calls) + "</ol>")

    # prognosis
    if p:
        o.append("<h2>5. Prognosis</h2>")
        xs = [t["day"] for t in p["trend"]] + [t["day"] for t in p["forecast"]]
        ymax = max(p["danger"] * 1.35, p["current"] * 1.2)
        vl = [(0, "today", "#52525b"), (p["onset_day"], "onset", "#a1a1aa")]
        if p["rul_days"]:
            vl.append((p["rul_days"], f"RUL {p['rul_days']} d", "#dc2626"))
        o.append(line_chart([([t["day"] for t in p["trend"]], [t["value"] for t in p["trend"]], "#0e7490", "", 1.4),
                             ([t["day"] for t in p["forecast"]], [t["value"] for t in p["forecast"]], "#be185d", "6 4", 2)],
                            (min(xs), max(xs)), (0, ymax), h=260, vlines=vl,
                            hlines=[(p["alert"], f"alert {p['alert']}", "#d97706"), (p["danger"], f"danger {p['danger']}", "#dc2626")],
                            bands=[(p["danger"], ymax, "#dc2626")], xlabel="days (0 = today)", ylabel=p["unit"]))
        o.append("<table>" + "".join(f"<tr><th>{k}</th><td>{E(str(val))}</td></tr>" for k, val in [
            ("Indicator", f"{p['indicator']} ({p['unit']})"), ("Current", p["current"]), ("Model", p["model"]),
            ("Growth", f"{p['growth_per_day'] * 100:.2f} %/day"),
            ("RUL to danger limit", "no growth" if p["rul_days"] is None else f"{p['rul_days']} days (95% band {p['rul_range'][0]}–{p['rul_range'][1]})")]) + "</table>")

    # work order
    if wo:
        o.append(f"<h2>6. Work order {E(wo['id'])} (revision {wo['revision']})</h2>"
                 f"<p><b>{E(wo['title'])}</b><br><span class='prio'>{wo['priority']}</span> · due within {wo['due_within_days']} days · "
                 f"{wo['estimated_hours']} h · {'drafted by LLM' if wo['mode'] == 'live' else 'template'}</p><p>{E(wo['justification'])}</p>")
        if wo.get("guardrail"):
            o.append(f"<div class='note warn'>{E(wo['guardrail'])}</div>")
        o.append("<div class='two'><div><h3>Tasks</h3><ol>" + "".join(f"<li>{E(t)}</li>" for t in wo["tasks"]) + "</ol></div><div><h3>Parts</h3><table>"
                 "<tr><th>Part</th><th>On hand</th><th>Location</th></tr>"
                 + "".join(f"<tr><td>{E(x['part'])}</td><td class='num'>{x['on_hand'] if x['on_hand'] is not None else '?'}</td><td>{E(x['location'])}</td></tr>" for x in wo["parts"])
                 + "</table><h3>Crew</h3><p>" + E(", ".join(wo["skills"])) + "</p><h3>Safety</h3><ul class='ev'>"
                 + "".join(f"<li>{E(s)}</li>" for s in wo["safety"]) + "</ul></div></div>")
        if rv:
            o.append(f"<div class='note {'ok' if rv['decision'] == 'approve' else 'warn'}'>{'Approved' if rv['decision'] == 'approve' else 'Rejected'} by "
                     f"{E(rv['reviewer'])} at {E(rv['at'])}{': “' + E(rv['comment']) + '”' if rv.get('comment') else ''}</div>")

    # log
    o.append("<h2>7. Agent audit log</h2><table><tr><th>Time (UTC)</th><th>Agent</th><th>Entry</th></tr>")
    for l in v.get("agent_log", []):
        o.append(f"<tr><td class='num'>{E(l['ts'][11:19])}</td><td>{E(NODES.get(l['agent'], (l['agent'],))[0])}</td>"
                 f"<td class='k-{E(l['kind'])}'>{E(l['text'])}</td></tr>")
    o.append("</table><footer>Generated by Vibration Diagnosis Agents (LangGraph). Signals are simulated for demonstration. "
             "To save as PDF, open this file in a browser and use Print → Save as PDF.</footer></div></body></html>")
    return "".join(o)
