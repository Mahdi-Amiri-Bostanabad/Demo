# Vibration Diagnosis Agents

A LangGraph multi-agent system for diagnosing rotating machinery from vibration data. The agents check signal quality, grade ISO 20816 severity, analyse the spectrum and envelope, diagnose the fault (an LLM with engineering tools), estimate remaining useful life, and draft a work order. A human approves the work order before it is released. The React UI shows the graph, the super-steps, every state channel and the engineering charts live.

## Run

```powershell
.\start.ps1
```

Open http://localhost:8090. The UI has two pages over the same backend and runs, and the switch in the header of both pages moves between them without losing the current run:

- **Commercial mode** (`/commercial`): a minimal showcase with machine and fault pickers, an animated machine diagram, the live agent graph, a one-line verdict with approval, and four engineering diagrams (spectrum, envelope, ISO zone, RUL trend).
- **Dev mode** (`/dev`): the full engineering view, with run settings, checkpoint timeline and time travel, state inspector, agent activity, LLM transcript and the full work order.

When a run finishes, both pages download a run report automatically (`vibration-report_<asset>_<run>.html`). It is one self-contained HTML file with the agent graph and path taken, signal charts, ISO severity, diagnosis, RUL trend, work order and audit log. Print it to get a PDF. A **Report** button and a card in the bottom right let you get it again; the endpoint is `GET /api/runs/{id}/report`.

`/` opens the last page used (commercial on the first visit). Add `?run=<thread_id>` to either URL to open a specific run.

On its first run the script creates `backend\.venv` (Python 3.12 via `uv`) and builds `frontend\dist`.

The LLM key lives in `backend\.env` (`AVALAI_API_KEY`, copied from `..\multiagent-predictive-maintenance\.env`). If AvalAI can't be reached, the LLM agents fall back to the rule engine, and the header pill says so.

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
