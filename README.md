# Agentic AI engineering demo

A demo of how agentic AI can help in engineering work.

| Folder | What it is |
| --- | --- |
| [`vibration-diagnosis-langgraph/`](vibration-diagnosis-langgraph/) | LangGraph + FastAPI + React app that diagnoses rotating-machinery vibration, with human approval and a downloadable run report. Its README explains how to run it and [how to use it in your own system](vibration-diagnosis-langgraph/README.md#use-it-in-your-own-system). |
| `.claude/skills/` | Project-level Claude Code skills: impeccable, ponytail and design-taste-frontend. They come from their own upstream repositories and keep their own licenses. |

## Secrets

The app reads its keys from a local `.env` file, which is gitignored.
