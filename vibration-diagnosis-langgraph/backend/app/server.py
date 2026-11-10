"""FastAPI server: starts graph runs, streams every LangGraph event to the UI over SSE,
exposes checkpoint history (time travel) and handles human-in-the-loop resume."""
from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import BaseMessage
from langgraph.types import Command
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from . import signals as S
from .graph import build_graph, graph_topology
from .llm import llm_status
from .machines import ASSETS, SCENARIOS, SEVERITY_LEVELS, get_asset, get_scenario
from .nodes import AGENTS
from .report import build_report

# Windows registries often map .js to text/plain, which browsers refuse for module scripts.
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")

GRAPH = build_graph()
app = FastAPI(title="Vibration Diagnosis Agents", version="1.0")


# --------------------------------------------------------------------------
# JSON helpers
# --------------------------------------------------------------------------

def jsonable(x: Any) -> Any:
    if isinstance(x, BaseMessage):
        d = {"type": x.type, "content": x.content if isinstance(x.content, str) else json.dumps(x.content)}
        if getattr(x, "tool_calls", None):
            d["tool_calls"] = [{"name": t["name"], "args": t["args"], "id": t["id"]} for t in x.tool_calls]
        if getattr(x, "name", None):
            d["name"] = x.name
        if getattr(x, "tool_call_id", None):
            d["tool_call_id"] = x.tool_call_id
        return d
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, (np.floating,)):
        return float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    if hasattr(x, "value") and hasattr(x, "id") and type(x).__name__ == "Interrupt":
        return {"value": jsonable(x.value), "id": x.id}
    return str(x)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# --------------------------------------------------------------------------
# Run manager: one asyncio task drives the graph, any number of SSE clients replay events
# --------------------------------------------------------------------------

@dataclass
class Run:
    thread_id: str
    config: dict
    meta: dict
    events: list = field(default_factory=list)
    status: str = "running"
    cond: asyncio.Condition = field(default_factory=asyncio.Condition)
    task: asyncio.Task | None = None

    async def emit(self, kind: str, **payload):
        async with self.cond:
            self.events.append({"seq": len(self.events), "kind": kind, "ts": _now(), **jsonable(payload)})
            self.cond.notify_all()


RUNS: dict[str, Run] = {}
STREAM_MODES = ["tasks", "updates", "custom", "checkpoints", "messages"]


async def drive(run: Run, graph_input: Any):
    run.status = "running"
    await run.emit("status", status="running")
    try:
        async for mode, chunk in GRAPH.astream(graph_input, run.config, stream_mode=STREAM_MODES):
            if mode == "tasks":
                if "input" in chunk:  # task start
                    await run.emit("task_start", node=chunk["name"], task_id=chunk["id"],
                                   triggers=list(chunk.get("triggers") or []))
                else:
                    await run.emit("task_end", node=chunk["name"], task_id=chunk["id"],
                                   error=str(chunk["error"]) if chunk.get("error") else None,
                                   interrupted=bool(chunk.get("interrupts")))
            elif mode == "updates":
                for node, upd in chunk.items():
                    if node == "__interrupt__":
                        await run.emit("interrupt", interrupts=upd)
                    else:
                        await run.emit("update", node=node, update=upd if isinstance(upd, dict) else {})
            elif mode == "custom":
                await run.emit("progress", **chunk)
            elif mode == "checkpoints":
                cfg = chunk["config"]["configurable"]
                meta = chunk.get("metadata") or {}
                await run.emit("checkpoint", checkpoint_id=cfg.get("checkpoint_id"), step=meta.get("step"),
                               source=meta.get("source"), next=list(chunk.get("next") or []),
                               values=chunk.get("values") or {})
            elif mode == "messages":
                msg, md = chunk
                text = msg.content if isinstance(msg.content, str) else ""
                tc = [t.get("name") for t in (getattr(msg, "tool_call_chunks", None) or []) if t.get("name")]
                if text or tc:
                    await run.emit("token", node=md.get("langgraph_node"), text=text, tool_calls=tc)
        snap = await GRAPH.aget_state(run.config)
        if snap.next:
            pending = [i for t in snap.tasks for i in (t.interrupts or [])]
            run.status = "interrupted"
            await run.emit("status", status="interrupted", next=list(snap.next), interrupts=pending)
        else:
            run.status = "done"
            await run.emit("status", status="done")
    except Exception as e:
        traceback.print_exc()
        run.status = "error"
        await run.emit("status", status="error", error=f"{type(e).__name__}: {e}")


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------

class StartRun(BaseModel):
    asset_id: str = "P-101"
    scenario: str = "misalignment"
    level: str = "moderate"
    location: str | None = None
    use_llm: bool = True
    pace: float = 0.8


class Resume(BaseModel):
    decision: str = "approve"
    comment: str = ""
    reviewer: str = "Reliability Engineer"


@app.get("/api/meta")
def meta():
    return {"assets": ASSETS, "scenarios": SCENARIOS, "levels": list(SEVERITY_LEVELS), "agents": AGENTS,
            "llm": llm_status()}


@app.get("/api/llm")
def llm(force: bool = False):
    return llm_status(force=force)


@app.get("/api/graph")
def graph():
    return graph_topology(GRAPH)


@app.post("/api/runs")
async def start_run(body: StartRun):
    try:
        asset = get_asset(body.asset_id)
        get_scenario(body.scenario)
    except KeyError as e:
        raise HTTPException(404, f"unknown {e}")
    tid = f"run-{uuid.uuid4().hex[:8]}"
    cfg = {"configurable": {"thread_id": tid, "use_llm": body.use_llm, "pace": max(0.0, min(body.pace, 3.0))},
           "recursion_limit": 80}
    location = body.location or asset["measurement_points"][2]
    run = Run(tid, cfg, {"asset_id": asset["id"], "scenario": body.scenario, "level": body.level,
                         "location": location, "use_llm": body.use_llm, "started_at": _now()})
    RUNS[tid] = run
    inp = {"asset": asset, "request": {"scenario": body.scenario, "level": body.level, "location": location,
                                        "requested_by": "Condition monitoring route"}}
    await run.emit("run_started", thread_id=tid, meta=run.meta, llm=llm_status())
    run.task = asyncio.create_task(drive(run, inp))
    return {"thread_id": tid}


@app.post("/api/runs/{tid}/resume")
async def resume(tid: str, body: Resume):
    run = RUNS.get(tid)
    if not run:
        raise HTTPException(404, "run not found")
    if run.status != "interrupted":
        raise HTTPException(409, f"run is {run.status}, not waiting for input")
    await run.emit("resume", decision=body.decision, comment=body.comment, reviewer=body.reviewer)
    run.task = asyncio.create_task(drive(run, Command(resume=body.model_dump())))
    return {"ok": True}


@app.get("/api/runs")
def list_runs():
    return [{"thread_id": r.thread_id, "status": r.status, **r.meta} for r in reversed(list(RUNS.values()))]


@app.get("/api/runs/{tid}/events")
async def events(tid: str, since: int = 0):
    run = RUNS.get(tid)
    if not run:
        raise HTTPException(404, "run not found")

    async def gen():
        i = since
        while True:
            async with run.cond:
                while i >= len(run.events):
                    try:
                        await asyncio.wait_for(run.cond.wait(), timeout=15)
                    except asyncio.TimeoutError:
                        break
                batch = run.events[i:]
            if not batch:
                yield {"event": "ping", "data": "{}"}
                continue
            for ev in batch:
                yield {"event": "message", "id": str(ev["seq"]), "data": json.dumps(ev)}
            i += len(batch)

    return EventSourceResponse(gen())


@app.get("/api/runs/{tid}/history")
async def history(tid: str):
    run = RUNS.get(tid)
    if not run:
        raise HTTPException(404, "run not found")
    out = []
    async for snap in GRAPH.aget_state_history(run.config):
        md = snap.metadata or {}
        out.append({
            "checkpoint_id": snap.config["configurable"]["checkpoint_id"],
            "parent_id": (snap.parent_config or {}).get("configurable", {}).get("checkpoint_id"),
            "step": md.get("step"), "source": md.get("source"),
            "writes": list((md.get("writes") or {}).keys()) if isinstance(md.get("writes"), dict) else None,
            "next": list(snap.next), "created_at": snap.created_at,
            "keys": sorted(snap.values.keys()),
        })
    return out


@app.get("/api/runs/{tid}/state")
async def state(tid: str, checkpoint_id: str | None = None):
    run = RUNS.get(tid)
    if not run:
        raise HTTPException(404, "run not found")
    cfg = {"configurable": {**run.config["configurable"]}}
    if checkpoint_id:
        cfg["configurable"]["checkpoint_id"] = checkpoint_id
    snap = await GRAPH.aget_state(cfg)
    return {"values": jsonable(snap.values), "next": list(snap.next),
            "checkpoint_id": snap.config["configurable"].get("checkpoint_id"),
            "step": (snap.metadata or {}).get("step")}


@app.get("/api/runs/{tid}/report")
async def run_report(tid: str, inline: bool = False):
    """One self-contained HTML file with the agent graph, charts, results, work order and audit log."""
    run = RUNS.get(tid)
    if not run:
        raise HTTPException(404, "run not found")
    snap = await GRAPH.aget_state(run.config)
    body = build_report(run, jsonable(snap.values), graph_topology(GRAPH))
    asset = snap.values.get("asset", {}).get("id", "asset")
    name = f"vibration-report_{asset}_{tid}.html"
    disp = "inline" if inline else "attachment"
    return HTMLResponse(body, headers={"Content-Disposition": f'{disp}; filename="{name}"'})


@app.get("/api/signals/{ref}")
def signal_preview(ref: str):
    if ref not in S.SIGNAL_STORE:
        raise HTTPException(404, "signal not found (server restarted?)")
    return S.previews(ref)


# --------------------------------------------------------------------------
# Static UI
# --------------------------------------------------------------------------

DIST = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.isdir(DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = os.path.join(DIST, path)
        if path and os.path.isfile(f):
            return FileResponse(f)
        return FileResponse(os.path.join(DIST, "index.html"))
