"""The shared LangGraph state.

Each key is a *channel*. Keys annotated with a reducer accumulate across nodes
and super-steps; plain keys are last-write-wins. Large data (raw waveforms,
spectra) lives outside the state in SIGNAL_STORE and is referenced by id.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


def merge_dicts(left: dict | None, right: dict | None) -> dict:
    return {**(left or {}), **(right or {})}


class VibState(TypedDict, total=False):
    # --- inputs ---------------------------------------------------------
    asset: dict                    # machine metadata incl. bearing geometry and ISO class
    request: dict                  # scenario, severity level, measurement point, requester

    # --- data acquisition ----------------------------------------------
    measurements: Annotated[list[dict], operator.add]   # append-only log of every reading
    rejected: Annotated[list[str], operator.add]        # measurement ids failed by QA
    pending_measurement: Optional[dict]                 # what acquisition should take next
    acquisition_attempts: int

    # --- analysis -------------------------------------------------------
    signal_quality: dict
    severity: dict                 # ISO 20816 assessment
    spectral: dict                 # features of radial (+ axial) readings
    hypotheses: list[dict]         # rule-based ranked candidates
    triage: dict                   # supervisor routing decision and reason

    # --- diagnosis (LLM tool loop) --------------------------------------
    messages: Annotated[list[AnyMessage], add_messages]
    diag_steps: int                # LLM calls in the current diagnosis round
    diagnosis_rounds: int
    diagnosis: Optional[dict]

    # --- prognosis and planning ----------------------------------------
    prognosis: dict
    work_order: Optional[dict]
    review: Optional[dict]         # human-in-the-loop decision
    plan_revisions: int

    # --- output and observability --------------------------------------
    report: dict
    agent_log: Annotated[list[dict], operator.add]
    llm_usage: Annotated[dict, merge_dicts]   # agent -> "live" | "fallback" | "rules"
