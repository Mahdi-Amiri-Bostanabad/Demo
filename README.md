# Agentic AI engineering demos

Two demos showing how agentic AI can help in engineering work.

| Folder | What it is |
| --- | --- |
| [`vibration-diagnosis-langgraph/`](vibration-diagnosis-langgraph/) | LangGraph + FastAPI + React app that diagnoses rotating-machinery vibration, with human approval and a downloadable run report. See its README. |
| [`multiagent-predictive-maintenance/`](multiagent-predictive-maintenance/) | MongoDB's multi-agent predictive maintenance demo (Failure, Work Order and Planning agents), with an added AvalAI provider for chat and embeddings. |
| `.claude/skills/` | Project-level Claude Code skills: impeccable, ponytail and design-taste-frontend. |

## Secrets

Each app reads its keys from a local `.env` file, which is gitignored. Copy the
`.env.example` where one exists and fill in your own keys.

## Third-party code

`multiagent-predictive-maintenance/` is copied from
[mongodb-industry-solutions/multiagent-predictive-maintenance](https://github.com/mongodb-industry-solutions/multiagent-predictive-maintenance)
at commit `fb1fc96` (MIT License, see its `LICENSE`). Local changes add the
`src/integrations/avalai` provider and wire it into the chat and embedding factories.

The skills in `.claude/skills/` come from their own upstream repositories and keep their own licenses.
