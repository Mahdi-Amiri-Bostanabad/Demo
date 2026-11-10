# Vibration Diagnosis Agents

A LangGraph multi-agent system for diagnosing rotating machinery from vibration data. The agents check signal quality, grade ISO 20816 severity, analyse the spectrum and envelope, diagnose the fault (an LLM with engineering tools), estimate remaining useful life, and draft a work order. A human approves the work order before it is released. The React UI shows the graph, the super-steps, every state channel and the engineering charts live.

- [Run the demo](#run)
- [Develop](#develop)
- [Layout](#layout)
- [Use it in your own system](#use-it-in-your-own-system)

## Run

```powershell
.\start.ps1
```

Open http://localhost:8090. The UI has two pages over the same backend and runs, and the switch in the header of both pages moves between them without losing the current run:

- **Commercial mode** (`/commercial`): a minimal showcase with machine and fault pickers, an animated machine diagram, the live agent graph, a one-line verdict with approval, and four engineering diagrams (spectrum, envelope, ISO zone, RUL trend).
- **Dev mode** (`/dev`): the full engineering view, with run settings, checkpoint timeline and time travel, state inspector, agent activity, LLM transcript and the full work order.

When a run finishes, both pages download a run report automatically (`vibration-report_<asset>_<run>.html`). It is one self-contained HTML file with the agent graph and path taken, signal charts, ISO severity, diagnosis, RUL trend, work order and audit log. Print it to get a PDF. A **Report** button and a card in the bottom right let you get it again; the endpoint is `GET /api/runs/{id}/report`. A sample is in [`docs/sample-run-report.html`](docs/sample-run-report.html).

`/` opens the last page used (commercial on the first visit). Add `?run=<thread_id>` to either URL to open a specific run.

On its first run the script creates `backend\.venv` (Python 3.12 via `uv`) and builds `frontend\dist`.

The LLM key lives in `backend\.env` (copy [`backend/.env.example`](backend/.env.example)). If the LLM can't be reached, the LLM agents fall back to the rule engine, and the header pill says so.

## Develop

```powershell
cd backend; .venv\Scripts\python.exe -m uvicorn app.server:app --port 8090 --reload
cd frontend; npm run dev   # http://localhost:5173, proxies /api to 8090
```

## Layout

- `backend/app/graph.py`: StateGraph wiring (fan-out and fan-in, loops, interrupt)
- `backend/app/state.py`: `VibState` channels and reducers
- `backend/app/nodes.py`: agents and routing functions
- `backend/app/tools.py`: tools for the diagnostician (InjectedState)
- `backend/app/signals.py`: signal synthesis and DSP
- `backend/app/knowledge.py`: fault knowledge base and rule engine
- `backend/app/machines.py`: assets, scenarios, ISO limits, spares, CMMS history
- `backend/app/report.py`: run report generator (inline SVG charts and graph, print-ready HTML)
- `backend/app/server.py`: FastAPI, SSE (tasks, updates, checkpoints, custom and messages stream modes), resume, history
- `frontend/src/App.tsx`: router between the two pages (path `/commercial` or `/dev`, remembered in localStorage)
- `frontend/src/pages/CommercialPage.tsx`: showcase page
- `frontend/src/pages/DevPage.tsx`: full engineering page
- `frontend/src/components`: graph, timeline, state inspector, activity feed and panels shared by the pages

The full design document (problem, solution, agentic workflow, state management) is a Claude Doc: https://claude.ai/artifact/M8iuuvVa8oswhVErrhyt7B

---

## Use it in your own system

This section is for engineers who want to run the agents on their own machines and data, or call them from their own software. It covers what is real and what is simulated, three ways to integrate, every place you need to plug in your own data, how to tune the engineering logic, and what to change before production.

### 1. What is real and what is simulated

The analysis pipeline is real. The data sources around it are stubs so the demo runs on its own.

| Part | Status | Where |
| --- | --- | --- |
| Signal QA (clipping, dead sensor, ski slope, DC offset, mount rattle) | Real | `signals.quality_checks` |
| Velocity RMS 10 to 1000 Hz, ISO 20816-3 zone grading | Real | `signals.velocity_rms`, `nodes.severity` |
| FFT order analysis, envelope (2 to 5 kHz, Hilbert) spectrum, bearing defect frequencies | Real | `signals.spectral_features`, `machines.bearing_frequencies` |
| Rule engine for unbalance, misalignment, looseness, outer race and inner race | Real, tunable | `knowledge.rule_hypotheses`, `knowledge.rule_diagnosis` |
| LLM diagnostician with tools, confidence gate, axial follow-up loop | Real | `nodes.diagnostician`, `tools.py`, `nodes.confidence_gate` |
| RUL model (exponential fit with a 95% band) | Real maths, simulated input | `nodes.prognosis` |
| Work order planner with policy guardrails, human approval, replan on reject | Real | `nodes.planner`, `nodes.human_review` |
| Run report (HTML, print to PDF) | Real | `report.py` |
| **Accelerometer waveforms** | **Simulated** (`signals.synthesize`) | replace, see 5.2 |
| **Asset catalogue** (3 example machines) | **Example data** | replace, see 5.1 |
| **120 day trend history** used by RUL | **Simulated** | replace, see 5.3 |
| **Spare parts stock and maintenance history** | **Example data** | replace, see 5.4 |
| **Work order hand-off to a CMMS** | **Not built** (the work order stays in the run state) | add, see 5.5 |

A "scenario" (healthy, unbalance, misalignment and so on) only tells the simulator which fault to synthesise. Once you feed real data, the scenario has no effect on the diagnosis.

### 2. Choose an integration route

| Route | When to use it | What you run |
| --- | --- | --- |
| **A. HTTP service** | Your system is not Python, or several systems need diagnoses | This backend as a service; your code calls the REST + SSE API |
| **B. Python library** | Your system is Python (a scheduler, a historian script, a notebook) | `build_graph()` imported into your process, no web server |
| **C. Fork and extend** | You want new faults, other machines, other tools or another approval flow | Change the nodes, tools and knowledge base, then use A or B |

Whichever route you take, you will need section 5 to connect real data. The UI is optional in all three; it is only a viewer for runs.

### 3. Install anywhere

Requirements: Python 3.12 (LangGraph 1.2 does not run on 3.8), Node 20 or newer for the UI only, and optionally an LLM endpoint.

**Windows:** `.\start.ps1` does everything below.

**Linux and macOS:**

```bash
cd backend
uv venv --python 3.12 .venv            # or: python3.12 -m venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env                   # then fill in the key
cd ../frontend && npm ci && npm run build   # optional, only for the UI
cd ../backend && .venv/bin/python -m uvicorn app.server:app --host 127.0.0.1 --port 8090
```

The server serves the built UI from `frontend/dist` when that folder exists, and only the API when it does not.

### 4. Configure the LLM

`backend/.env` holds three settings, read by `backend/app/llm.py`:

| Variable | Meaning | Default |
| --- | --- | --- |
| `AVALAI_API_KEY` | API key for the endpoint | none (LLM agents fall back to rules) |
| `AVALAI_BASE_URL` | Any **OpenAI-compatible** base URL | `https://api.avalai.ir/v1` |
| `LLM_MODEL` | Model name at that endpoint | `claude-haiku-5-5` |

The client is LangChain's `ChatOpenAI`, so any OpenAI-compatible server works without code changes: OpenAI itself (`https://api.openai.com/v1`), a LiteLLM proxy, vLLM, Ollama (`http://localhost:11434/v1`) or LM Studio. The variable names say AvalAI only for historical reasons. The model must support tool calling, because the diagnostician works through tools and the planner uses function calling for structured output. For a provider with its own SDK (Anthropic, Azure OpenAI, Bedrock), change `get_llm()` in `llm.py` to return that LangChain chat model; nothing else depends on the provider.

**What is sent to the LLM:** asset metadata (id, name, type, site, criticality, rpm, bearing model), computed features (overall levels, order amplitudes, envelope SNRs, time statistics), the rule engine's ranking, maintenance history, spare parts stock and reviewer comments. Raw waveforms are never sent. If that is still too much for your data policy, use a self-hosted model or turn the LLM off.

**Running without an LLM:** pass `use_llm: false` per run (API) or `"use_llm": False` in the config (library). The diagnostician then uses the rule engine and the planner uses a template. Every agent records which mode it ran in, in the `llm_usage` state channel (`live`, `fallback` or `rules`), and the report shows it. When the endpoint is unreachable, runs fall back automatically.

### 5. Connect your own data

#### 5.1 Your machines (asset catalogue)

An asset is a plain dict. Every field below is used somewhere, so keep all of them:

```python
{
    "id": "P-101",                                # your tag; also used in work order ids
    "name": "Cooling Water Pump P-101",
    "type": "Centrifugal pump, overhung, motor driven",
    "site": "Utilities Unit 1",
    "rpm": 1780,                                  # running speed; drives orders and bearing frequencies
    "power_kw": 75,
    "iso_group": "group2",                        # ISO 20816-3: group1 (>300 kW) or group2 (15-300 kW)
    "foundation": "rigid",                        # "rigid" or "flexible"
    "coupling": "Flexible disc coupling",
    "bearing": {"model": "SKF 6309", "n_balls": 8, "ball_d_mm": 17.46,
                "pitch_d_mm": 72.5, "contact_deg": 0.0},   # geometry from the bearing catalogue
    "criticality": "High: single train, no installed spare",
    "measurement_points": ["Motor NDE", "Motor DE", "Pump DE", "Pump NDE"],
}
```

To load your own machines, replace `ASSETS` and `get_asset()` in `machines.py` with a lookup in your asset register (a CMMS, an EAM such as SAP PM or Maximo, or a JSON file). With the library route you can skip the lookup and pass the dict straight into the graph input. Bearing geometry is what makes BPFO and BPFI correct, so take it from the manufacturer's data for the bearing actually installed. The demo assumes one monitored bearing per machine; for machines with different bearings at each end, put the geometry per measurement point and pick it in `spectral_features`.

#### 5.2 Your vibration measurements (the main change)

All signal data enters through one call in the `acquisition` node (`nodes.py`):

```python
ref = S.acquire(state["asset"], scenario["fault"], req["level"], location, direction, seed, sensor_fault)
```

`S.acquire` synthesises a waveform and stores it in `SIGNAL_STORE` under a reference id. Every downstream agent reads the waveform through that id only, so the state and its checkpoints stay small. Replace this call with your own function that fetches a real waveform and stores it the same way:

```python
# signals.py
def store_waveform(acc_m_s2: np.ndarray, fs: int, rpm: float) -> str:
    ref = f"sig_{uuid.uuid4().hex[:10]}"
    SIGNAL_STORE[ref] = {"acc": acc_m_s2, "fs": fs, "rpm": rpm}
    return ref

# nodes.py, inside acquisition()
acc, fs, rpm = await my_historian.latest_waveform(state["asset"]["id"], location, direction)
ref = S.store_waveform(acc, fs, rpm)
```

Requirements for the waveform:

- **Units:** acceleration in m/s² (multiply by 9.80665 if your system gives g). Velocity is obtained by integration in the frequency domain.
- **Sample rate:** at least 10.24 kHz. The envelope band is 2 to 5 kHz, so lower rates lose bearing diagnostics. The demo uses 20.48 kHz.
- **Length:** at least about 1.6 s. Resolution is fs / N; 0.625 Hz is enough to separate orders on machines above roughly 600 rpm. Slow machines need longer records.
- **Speed:** the `rpm` stored with the waveform should be the measured speed if you have a tachometer. `spectral_features` currently uses `asset["rpm"]`, so for variable speed machines pass the measured speed into it instead.
- **Direction:** the strings `"Horizontal"`, `"Vertical"` and `"Axial"` are used. Any non-axial reading is treated as radial.

Also update the `fs_hz`, `samples` and `rpm` fields of the measurement record in the same node (they are currently taken from the simulator's constants), and remove the `seed`, `sensor_fault` and `scenario` lines, which only exist for the simulator.

**Where the data can come from:** an online monitoring system or historian (OSIsoft PI, AVEVA, Emerson AMS, SKF @ptitude, Bently Nevada System 1 export), a wireless sensor platform's API, files dropped by a route collector (CSV, WAV, UFF), or a DAQ card (NI-DAQmx). If your system only stores overall values and spectra, not waveforms, the severity grading still works, but envelope analysis needs a time waveform.

**Follow-up readings:** when the diagnosis is uncertain between unbalance and misalignment, the confidence gate sets `pending_measurement = {"location": ..., "direction": "Axial", "purpose": ...}` and loops back to `acquisition`. With an online system, fetch the axial channel. With route-based data collection a person has to take the reading: call LangGraph's `interrupt()` in `acquisition` with the request (the same way `human_review` does), let your system create a task for the technician, and resume the run with the new waveform reference once it is uploaded.

**Signal QA thresholds** are in `signals.quality_checks` and assume a 50 g full scale sensor (`FULL_SCALE_G`). Set that to your sensor's range.

#### 5.3 Trend history for remaining useful life

`nodes.prognosis` builds a 120 day trend from a random generator, then fits an exponential degradation model to it. Replace the block that builds `days` and `y` with a query to your historian for the same indicator: the overall velocity RMS (mm/s) for shaft faults, or the envelope amplitude at BPFO or BPFI (gE) for bearing faults. Give it one value per day, oldest first, with today's value last. Set `onset` to the first day the indicator left its baseline (or detect it, for example the first day above the baseline plus three standard deviations). The `alert`, `danger` and `baseline` values in that function are the limits the RUL is measured against; set them from your site's alarm philosophy.

#### 5.4 Spare parts and maintenance history

`SPARE_PARTS` and `MAINTENANCE_HISTORY` in `machines.py` are static dicts. They are read by the `get_maintenance_history` tool, by the planner prompt and by `_resolve_parts` in `nodes.py`. Replace them with functions that query your ERP or CMMS, keeping the shapes:

```python
SPARE_PARTS["SKF 6309"] == {"on_hand": 2, "location": "Main store, bin B-14", "lead_time_days": 0}
MAINTENANCE_HISTORY["P-101"] == [{"date": "2026-03-14", "type": "PM", "summary": "..."}, ...]
```

The planner is told to use exact catalogue names in `parts`, so the part names in your stock list must match the names in `FAULT_KB[...]["parts"]` in `knowledge.py` (the word `"bearing"` is resolved to the asset's bearing model).

#### 5.5 Sending the approved work order to your CMMS

The run ends with a work order in `state["work_order"]` and a summary in `state["report"]`:

```python
work_order = {
    "id": "WO-P-101-01", "asset_id": "P-101", "fault": "outer_race",
    "title": "...", "priority": "P1", "due_within_days": 2,
    "tasks": ["Isolate and lock out motor (LOTO), verify zero energy", "..."],
    "parts": [{"part": "SKF 6309", "on_hand": 2, "location": "...", "lead_time_days": 0}],
    "estimated_hours": 8, "skills": ["..."], "safety": ["..."], "justification": "...",
    "revision": 1, "mode": "live", "guardrail": None, "requires_approval": True,
}
report = {"status": "action_required", "headline": "...", "generated_at": "...", "path": ["acquisition", "..."]}
```

`report["status"]` is one of `healthy`, `action_required`, `on_hold` (the reviewer rejected the final revision) or `inconclusive` (no valid measurement). The approval itself is in `state["review"]` (`decision`, `comment`, `reviewer`, `at`).

There are two ways to hand it over:

- **From outside (simplest):** after the run reaches `done`, read `GET /api/runs/{id}/state` and post the work order to your CMMS API (SAP PM notification, Maximo work order, Fiix, UpKeep, or an email to the planner). Attach the HTML from `GET /api/runs/{id}/report`.
- **Inside the graph:** add a `cmms_export` node between `human_review` and `report`, so only approved work orders are sent and the CMMS reply (its work order number) is saved in the state and the report. In `graph.py`, change the `human_review` route to go to `cmms_export` on approval, and add `g.add_edge("cmms_export", "report")`.

#### 5.6 Starting runs automatically

A run is started by `POST /api/runs` (or `graph.ainvoke` in the library route). Typical triggers: a scheduler that runs every monitored machine once a day or once a week, an alarm from your online system when an overall level crosses its alert limit, or a button in your own HMI or dashboard. Use a meaningful `thread_id` in the library route (for example `P-101-2026-11-11`) so that runs can be traced later.

### 6. API reference (route A)

All endpoints are JSON unless noted. There is no authentication; see section 9.

| Method and path | Purpose |
| --- | --- |
| `GET /api/meta` | Assets, scenarios, severity levels, agent names, LLM status |
| `GET /api/llm?force=true` | LLM reachability (force re-probes now) |
| `GET /api/graph` | Graph topology: nodes, edges, Mermaid source |
| `POST /api/runs` | Start a run. Returns `{"thread_id": "run-…"}` |
| `GET /api/runs` | All runs in this server process, newest first |
| `GET /api/runs/{id}/events?since=N` | Server-sent events for the run, replayed from event `N` |
| `POST /api/runs/{id}/resume` | Answer the approval interrupt |
| `GET /api/runs/{id}/state?checkpoint_id=…` | Full state, now or at a past checkpoint |
| `GET /api/runs/{id}/history` | Every checkpoint (for time travel and audit) |
| `GET /api/runs/{id}/report?inline=true` | Self-contained HTML report (attachment unless `inline`) |
| `GET /api/signals/{ref}` | Downsampled waveform, spectrum and envelope for charts |

**Start a run** (`POST /api/runs`). All fields are optional:

```json
{"asset_id": "P-101", "scenario": "misalignment", "level": "moderate",
 "location": "Pump DE", "use_llm": true, "pace": 0}
```

`pace` adds a delay in seconds per step so the UI can be watched. Set it to `0` for machine use. `location` defaults to the asset's third measurement point. `scenario` and `level` only matter for the simulator.

**Events** (`GET /api/runs/{id}/events`). Each SSE message has `data` with `seq`, `kind`, `ts` and fields for that kind. Ping messages carry `{}`.

| `kind` | Fields | Meaning |
| --- | --- | --- |
| `run_started` | `thread_id`, `meta`, `llm` | Run accepted |
| `status` | `status` (`running`, `interrupted`, `done`, `error`), `interrupts`, `error` | Lifecycle. Watch for this |
| `task_start`, `task_end` | `node`, `task_id`, `error`, `interrupted` | An agent started or finished |
| `update` | `node`, `update` | The state keys an agent wrote |
| `checkpoint` | `checkpoint_id`, `step`, `next`, `values` | A saved super-step |
| `progress` | `agent`, `text` | Human-readable progress line |
| `token` | `node`, `text`, `tool_calls` | Streamed LLM output |
| `interrupt` | `interrupts` | The graph paused for a person |
| `resume` | `decision`, `comment`, `reviewer` | Someone answered |

**Approve or reject** (`POST /api/runs/{id}/resume`), only while the run's status is `interrupted`:

```json
{"decision": "approve", "comment": "", "reviewer": "J. Smith"}
```

With `"decision": "reject"`, the comment goes back to the planner as feedback and a revised work order comes back for approval, up to two revisions.

**Complete client example** (Python with `httpx`; the same flow works from any language with HTTP and SSE):

```python
import json
import httpx

BASE = "http://localhost:8090"


def wait_for_status(tid: str, since: int = 0) -> dict:
    """Read the run's event stream until it pauses for approval, finishes or fails."""
    with httpx.stream("GET", f"{BASE}/api/runs/{tid}/events", params={"since": since}, timeout=None) as r:
        for line in r.iter_lines():
            if not line.startswith("data:"):
                continue
            ev = json.loads(line[5:])
            if ev.get("kind") == "status" and ev["status"] in ("interrupted", "done", "error"):
                return ev


tid = httpx.post(f"{BASE}/api/runs", json={"asset_id": "P-101", "use_llm": True, "pace": 0}).json()["thread_id"]

ev = wait_for_status(tid)
if ev["status"] == "interrupted":
    print("Needs approval:", ev["interrupts"][0]["value"]["question"])
    httpx.post(f"{BASE}/api/runs/{tid}/resume",
               json={"decision": "approve", "comment": "", "reviewer": "J. Smith"}).raise_for_status()
    ev = wait_for_status(tid, since=ev["seq"] + 1)

state = httpx.get(f"{BASE}/api/runs/{tid}/state").json()["values"]
print(ev["status"], "|", state["report"]["headline"])
open(f"report_{tid}.html", "w", encoding="utf-8").write(httpx.get(f"{BASE}/api/runs/{tid}/report").text)
```

In a real integration the approval usually comes from a person in your own tool (a CMMS approval step, a Teams or Slack button, an email link) rather than from code. Store the `thread_id`, show the work order from `/state`, and call `/resume` with their answer whenever it arrives. The run waits as long as needed.

### 7. Use it as a Python library (route B)

Run this from the `backend` folder (or add it to `PYTHONPATH`) with the backend's virtual environment:

```python
import asyncio
from langgraph.types import Command
from app.graph import build_graph
from app.machines import get_asset


async def main():
    graph = build_graph()                       # pass checkpointer=... for persistence, see section 9
    cfg = {"configurable": {"thread_id": "P-101-2026-11-11", "use_llm": True, "pace": 0},
           "recursion_limit": 80}
    asset = get_asset("P-101")                  # or your own asset dict (section 5.1)
    inp = {"asset": asset,
           "request": {"scenario": "misalignment", "level": "moderate",
                       "location": asset["measurement_points"][2], "requested_by": "Nightly scheduler"}}

    state = await graph.ainvoke(inp, cfg)
    if "__interrupt__" in state:                # paused for work order approval
        print(state["__interrupt__"][0].value["question"])
        state = await graph.ainvoke(Command(resume={"decision": "approve", "comment": "", "reviewer": "J. Smith"}), cfg)

    print(state["report"]["status"], state["report"]["headline"])
    print(state["work_order"]["id"], state["work_order"]["priority"])


asyncio.run(main())
```

The two `ainvoke` calls can be far apart in time, and even in different processes if you use a persistent checkpointer: resuming only needs the same `thread_id`. The HTML report is built from the server's event log (`report.build_report` takes the server's `Run` object, which holds the streamed events), so the library route does not produce it directly. Either use the API route when you need the report, or collect the same events yourself with `graph.astream(..., stream_mode=["tasks", "updates", "custom", "checkpoints", "messages"])` as `server.drive` does.

### 8. Tune the engineering logic (route C)

| What | Where |
| --- | --- |
| ISO 20816-3 zone limits per group and foundation | `ISO_20816_LIMITS` in `machines.py` |
| Fault signatures, confirmation checks, corrective actions, parts, hours, skills | `FAULT_KB` in `knowledge.py` |
| Rule scores and thresholds (for example 2X/1X > 0.4 for misalignment) | `rule_hypotheses` and `rule_diagnosis` in `knowledge.py` |
| When triage takes the healthy fast path (zone A/B, top rule < 0.35, kurtosis < 4) | `triage` in `nodes.py` |
| When the confidence gate asks for an axial reading (confidence < 0.7) | `confidence_gate` in `nodes.py` |
| Priority policy (P1 for zone D or RUL ≤ 7 days, and so on) | `_policy_priority` in `nodes.py` |
| Which priorities need human approval (P1 and P2) | `requires_approval` in `planner` |
| Retry and loop budgets | `MAX_DIAG_STEPS`, `MAX_ACQ_ATTEMPTS`, `MAX_DIAG_ROUNDS`, `MAX_PLAN_REVISIONS` at the top of `nodes.py` |
| The diagnostician's instructions | `DIAG_SYSTEM` in `nodes.py` |

The planner's guardrail always enforces the policy priority, whatever the LLM drafts: the LLM can make a work order more urgent, never less.

**Adding a fault type** (for example gear mesh or electrical faults): add an entry to `FAULT_KB`, add a scoring block in `rule_hypotheses`, add the name to the `FaultName` literal in `tools.py`, mention its signature in `DIAG_SYSTEM`, and add any tool the diagnostician needs to check it (for example gear mesh frequency sidebands). Add a simulator case in `signals.synthesize` if you still want to demo it without real data.

**Adding a tool:** write a function with LangChain's `@tool` decorator in `tools.py`. Take the state with `Annotated[dict, InjectedState]` so the LLM does not have to pass data around, return JSON text, and add it to `INVESTIGATION_TOOLS`.

**Adding or removing a graph node:** wire it in `graph.py`. The UI and the report draw the graph from fixed positions, so also add the node to `frontend/src/meta.ts` and to the positions in `report.py`.

### 9. Before production

This is a demonstrator. It is not a certified condition monitoring system, and its diagnoses are decision support for a qualified analyst. These are the gaps to close:

- **Persistence.** Runs, checkpoints and waveforms are held in memory, so a restart loses them. Use a persistent LangGraph checkpointer (`langgraph-checkpoint-postgres` or `langgraph-checkpoint-sqlite`) and pass it to `build_graph(checkpointer=...)`, move `SIGNAL_STORE` to object storage or your historian (keep the reference-id pattern), and store the `RUNS` event log in a database or Redis.
- **One worker.** The run registry lives in the server process, so run uvicorn with a single worker until it is moved out (or put a queue such as Celery or Arq in front).
- **Security.** There is no authentication, authorisation or CORS configuration, and the server binds to `127.0.0.1` on purpose. Put it behind your SSO or an API gateway before exposing it, and record the real reviewer identity from that login instead of the free-text `reviewer` field.
- **Secrets.** Keep keys in `backend/.env` or your secret manager, never in the repository (`.env` is gitignored).
- **Validation.** Validate the rules and thresholds against your own machines' history and known faults before trusting the priorities, and keep the human approval step.
- **Audit.** `agent_log`, the checkpoint history and the HTML report together record who and what decided each step. Archive the report with the work order.
- **Monitoring.** LangGraph runs can be traced with LangSmith by setting `LANGSMITH_API_KEY` and `LANGSMITH_TRACING=true`, or you can log the `/events` stream.
