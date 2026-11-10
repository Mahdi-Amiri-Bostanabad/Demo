"""Agent nodes of the vibration diagnosis graph.

Each node is one agent with one responsibility. A node reads the state, does its
work (DSP, rules, LLM reasoning or a human interrupt) and returns a *partial*
state update. LangGraph merges that update through the channel reducers and
writes a checkpoint after every super-step.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
from datetime import datetime, timezone

import numpy as np
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.types import interrupt
from pydantic import BaseModel, Field
from typing import Literal

from . import signals as S
from .knowledge import FAULT_KB, rule_diagnosis, rule_hypotheses
from .llm import get_llm, llm_status
from .machines import (MAINTENANCE_HISTORY, SPARE_PARTS, ZONE_TEXT, bearing_frequencies,
                       get_scenario, iso_limits)
from .state import VibState
from .tools import ALL_DIAG_TOOLS

MAX_DIAG_STEPS = 8
MAX_ACQ_ATTEMPTS = 3
MAX_DIAG_ROUNDS = 2
MAX_PLAN_REVISIONS = 2

AGENTS = {
    "acquisition": "Data Acquisition Agent",
    "signal_qa": "Signal Quality Agent",
    "severity": "ISO 20816 Severity Agent",
    "spectral": "Spectral Analysis Agent",
    "triage": "Supervisor (Triage)",
    "diagnostician": "Diagnostician (LLM)",
    "diag_tools": "Engineering Toolbox",
    "confidence_gate": "Supervisor (Confidence Gate)",
    "prognosis": "Prognosis / RUL Agent",
    "planner": "Maintenance Planner (LLM)",
    "human_review": "Reliability Engineer (Human)",
    "report": "Report Agent",
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _log(agent: str, text: str, kind: str = "info", **data) -> dict:
    return {"ts": _now(), "agent": agent, "kind": kind, "text": text, **({"data": data} if data else {})}


def _emit(agent: str, text: str):
    """Fine-grained progress, streamed to the UI with stream_mode='custom'. Not stored in state."""
    try:
        get_stream_writer()({"type": "progress", "agent": agent, "text": text})
    except Exception:
        pass


async def _pace(config: RunnableConfig, factor: float = 1.0):
    p = float(config.get("configurable", {}).get("pace", 0.0))
    if p > 0:
        await asyncio.sleep(p * factor)


def _use_llm(config: RunnableConfig) -> bool:
    if not config.get("configurable", {}).get("use_llm", True):
        return False
    return bool(llm_status()["available"])


def _valid(state) -> list[dict]:
    rej = set(state.get("rejected", []))
    return [m for m in state.get("measurements", []) if m["id"] not in rej]


def _seed(*parts) -> int:
    return int(hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


# --------------------------------------------------------------------------
# 1. Data acquisition
# --------------------------------------------------------------------------

async def acquisition(state: VibState, config: RunnableConfig) -> dict:
    agent = "acquisition"
    req = state["request"]
    scenario = get_scenario(req["scenario"])
    attempt = state.get("acquisition_attempts", 0)
    pending = state.get("pending_measurement") or {}
    location = pending.get("location") or req["location"]
    direction = pending.get("direction") or "Horizontal"
    purpose = pending.get("purpose") or "Routine route measurement"
    sensor_fault = bool(scenario.get("sensor_fault_first")) and attempt == 0

    _emit(agent, f"Triggering wireless accelerometer at {location} ({direction})")
    await _pace(config, 0.6)
    seed = _seed(config["configurable"].get("thread_id"), attempt, direction)
    ref = S.acquire(state["asset"], scenario["fault"], req["level"], location, direction, seed, sensor_fault)
    _emit(agent, f"Captured {S.N} samples @ {S.FS} Hz ({S.N / S.FS:.1f} s)")
    await _pace(config, 0.4)
    tf = S.time_features(ref)
    vrms = round(S.velocity_rms(ref), 3)
    m = {
        "id": f"M{attempt + 1}",
        "signal_ref": ref,
        "location": location,
        "direction": direction,
        "purpose": purpose,
        "taken_at": _now(),
        "fs_hz": S.FS,
        "samples": S.N,
        "rpm": state["asset"]["rpm"],
        "features": {**tf, "velocity_rms_mm_s": vrms},
    }
    return {
        "measurements": [m],
        "acquisition_attempts": attempt + 1,
        "pending_measurement": None,
        "agent_log": [_log(agent, f"Measurement {m['id']} at {location} {direction}: {vrms} mm/s RMS, "
                                  f"kurtosis {tf['kurtosis']}. Purpose: {purpose.rstrip('. ')}.", signal_ref=ref)],
    }


# --------------------------------------------------------------------------
# 2. Signal quality
# --------------------------------------------------------------------------

async def signal_qa(state: VibState, config: RunnableConfig) -> dict:
    agent = "signal_qa"
    m = state["measurements"][-1]
    _emit(agent, f"Validating {m['id']}: clipping, ski slope, DC offset, mount rattle")
    await _pace(config, 0.7)
    checks = S.quality_checks(m["signal_ref"])
    ok = all(c["ok"] for c in checks)
    failed = [c["name"] for c in checks if not c["ok"]]
    out = {"signal_quality": {"measurement_id": m["id"], "verdict": "pass" if ok else "fail", "checks": checks}}
    if ok:
        out["agent_log"] = [_log(agent, f"{m['id']} passed all {len(checks)} quality checks.", "decision")]
    else:
        attempts = state.get("acquisition_attempts", 0)
        retry = attempts < MAX_ACQ_ATTEMPTS
        out["rejected"] = [m["id"]]
        if retry:
            out["pending_measurement"] = {"location": m["location"], "direction": m["direction"],
                                          "purpose": "Re-acquire after QA reject: technician asked to re-seat the magnet mount"}
        out["agent_log"] = [_log(agent, f"{m['id']} REJECTED ({', '.join(failed)}). "
                                        + ("Requesting re-acquisition." if retry else "Retry budget exhausted."),
                                 "warn")]
    return out


def route_after_qa(state: VibState):
    if state["signal_quality"]["verdict"] == "pass":
        return ["severity", "spectral"]  # fan out: both run in the same super-step
    if state.get("acquisition_attempts", 0) < MAX_ACQ_ATTEMPTS:
        return "acquisition"
    return "report"


# --------------------------------------------------------------------------
# 3a. ISO 20816 severity (parallel branch)
# --------------------------------------------------------------------------

async def severity(state: VibState, config: RunnableConfig) -> dict:
    agent = "severity"
    asset = state["asset"]
    _emit(agent, "Integrating acceleration to velocity, 10-1000 Hz band")
    await _pace(config, 0.9)
    valid = _valid(state)
    worst = max(valid, key=lambda m: m["features"]["velocity_rms_mm_s"])
    v = worst["features"]["velocity_rms_mm_s"]
    ab, bc, cd = iso_limits(asset)
    zone = "A" if v < ab else "B" if v < bc else "C" if v < cd else "D"
    sev = {
        "velocity_rms_mm_s": v,
        "governing_measurement": worst["id"],
        "zone": zone,
        "zone_text": ZONE_TEXT[zone],
        "limits": {"A/B": ab, "B/C": bc, "C/D": cd},
        "standard": f"ISO 20816-3, {asset['iso_group'].replace('group', 'Group ')}, {asset['foundation']} foundation",
        "per_measurement": {m["id"]: m["features"]["velocity_rms_mm_s"] for m in valid},
    }
    return {"severity": sev,
            "agent_log": [_log(agent, f"Overall {v} mm/s RMS ({worst['id']}) is Zone {zone}: {ZONE_TEXT[zone]}.",
                               "decision")]}


# --------------------------------------------------------------------------
# 3b. Spectral analysis (parallel branch)
# --------------------------------------------------------------------------

async def spectral(state: VibState, config: RunnableConfig) -> dict:
    agent = "spectral"
    asset = state["asset"]
    valid = _valid(state)
    radial = [m for m in valid if m["direction"] != "Axial"][-1]
    axial = ([m for m in valid if m["direction"] == "Axial"] or [None])[-1]
    _emit(agent, f"FFT of {radial['id']} (Hann, {S.FS / S.N:.3f} Hz resolution)")
    await _pace(config, 0.5)
    rs = S.spectral_features(radial["signal_ref"], asset)
    _emit(agent, "Envelope demodulation 2-5 kHz, Hilbert transform, envelope FFT")
    await _pace(config, 0.6)
    ax = S.spectral_features(axial["signal_ref"], asset) if axial else None
    rs["measurement_id"] = radial["id"]
    if ax:
        ax["measurement_id"] = axial["id"]
    hyps = rule_hypotheses(rs, radial["features"], ax)
    top = hyps[0]
    return {
        "spectral": {"radial": rs, "axial": ax},
        "hypotheses": hyps,
        "agent_log": [_log(agent, f"1X {rs['orders_mm_s']['1X']} mm/s, 2X {rs['orders_mm_s']['2X']} mm/s, "
                                  f"{rs['harmonic_count']} harmonics. Rule prior: {top['fault']} ({top['score']}).")],
    }


# --------------------------------------------------------------------------
# 4. Supervisor triage (join point of the parallel branches)
# --------------------------------------------------------------------------

async def triage(state: VibState, config: RunnableConfig) -> dict:
    agent = "triage"
    await _pace(config, 0.4)
    sev, hyps = state["severity"], state["hypotheses"]
    radial = state["spectral"]["radial"]
    kurt = [m for m in _valid(state) if m["id"] == radial["measurement_id"]][0]["features"]["kurtosis"]
    if state.get("diagnosis_rounds", 0) > 0:
        route, why = "diagnose", "Follow-up measurement arrived; diagnostician re-evaluates with the new evidence."
    elif sev["zone"] in ("A", "B") and hyps[0]["score"] < 0.35 and kurt < 4:
        route, why = "healthy", (f"Zone {sev['zone']}, no fault rule above 0.35, kurtosis {kurt}. "
                                 "Healthy fast path: skip diagnosis and planning.")
    else:
        bits = []
        if sev["zone"] in ("C", "D"):
            bits.append(f"Zone {sev['zone']}")
        if hyps[0]["score"] >= 0.35:
            bits.append(f"{hyps[0]['fault']} prior {hyps[0]['score']}")
        if kurt >= 4:
            bits.append(f"kurtosis {kurt} (impacting)")
        route, why = "diagnose", "Abnormal: " + ", ".join(bits) + ". Escalating to diagnostician."
    return {"triage": {"route": route, "reason": why},
            "agent_log": [_log(agent, why, "decision")]}


def route_after_triage(state: VibState):
    return "report" if state["triage"]["route"] == "healthy" else "diagnostician"


# --------------------------------------------------------------------------
# 5. Diagnostician: LLM with tool loop, rules as fallback
# --------------------------------------------------------------------------

DIAG_SYSTEM = """You are an ISO 18436 Category III vibration analyst working as one agent inside a LangGraph
multi-agent condition-monitoring system. Upstream agents already acquired the data, validated it, graded
ISO 20816 severity and extracted spectral features. Your job: determine the fault.

Method:
- Verify evidence with the tools. Never invent numbers.
- Unbalance: dominant radial 1X, 2X/1X < 0.3, low axial.
- Misalignment: 2X/1X > 0.5 and/or axial 1X or 2X > 50% of radial 1X.
- Looseness: many 1X harmonics, 0.5X subharmonics, raised floor.
- Bearing defects show in the envelope spectrum (SNR > 6 at BPFO or BPFI, harmonics) and high kurtosis even when
  velocity is low. Inner race shows 1X sidebands around BPFI.
- If unbalance vs misalignment cannot be separated because there is no axial reading yet, call submit_diagnosis
  with request_axial_measurement=true and confidence <= 0.6.
Use at most 6 investigation tool calls, then call submit_diagnosis exactly once. Keep any prose to one or two
short sentences explaining what you are checking next."""


def _diag_brief(state: VibState) -> str:
    a, sev, hyps = state["asset"], state["severity"], state["hypotheses"]
    r = state["spectral"]["radial"]
    return (f"Asset {a['id']} {a['name']} ({a['type']}), {a['rpm']} rpm, bearing {a['bearing']['model']}.\n"
            f"Severity: {sev['velocity_rms_mm_s']} mm/s RMS, ISO zone {sev['zone']} ({sev['standard']}).\n"
            f"Radial measurement {r['measurement_id']}: 1X {r['orders_mm_s']['1X']}, 2X {r['orders_mm_s']['2X']} mm/s.\n"
            f"Axial measurement available: {'yes' if state['spectral'].get('axial') else 'no'}.\n"
            "Rule-engine prior (verify, do not trust blindly): "
            + "; ".join(f"{h['fault']}={h['score']}" for h in hyps[:4]))


def _normalize_diag(args: dict, rounds: int, mode: str) -> dict:
    fault = args.get("primary_fault", "healthy")
    req = None
    if args.get("request_axial_measurement"):
        req = {"location": "same", "direction": "Axial",
               "reason": args.get("request_reason") or "Separate competing hypotheses"}
    return {
        "primary_fault": fault,
        "fault_title": FAULT_KB.get(fault, FAULT_KB["healthy"])["title"],
        "confidence": round(float(args.get("confidence", 0.5)), 2),
        "evidence": list(args.get("evidence") or [])[:8],
        "rationale": args.get("rationale", ""),
        "secondary_faults": list(args.get("secondary_faults") or []),
        "request_measurement": req,
        "round": rounds + 1,
        "mode": mode,
    }


def _rule_fallback(state: VibState, rounds: int, mode: str, note: str) -> dict:
    have_axial = bool(state["spectral"].get("axial"))
    d = rule_diagnosis(state["hypotheses"], have_axial)
    d = _normalize_diag({**d, "request_axial_measurement": bool(d.get("request_measurement")),
                         "request_reason": (d.get("request_measurement") or {}).get("reason", "")}, rounds, mode)
    return {
        "diagnosis": d,
        "diagnosis_rounds": rounds + 1,
        "diag_steps": 0,
        "llm_usage": {"diagnostician": mode},
        "agent_log": [_log("diagnostician", f"{note} Rule-based diagnosis: {d['fault_title']} "
                                            f"(confidence {d['confidence']}).", "decision")],
    }


async def diagnostician(state: VibState, config: RunnableConfig) -> dict:
    agent = "diagnostician"
    rounds = state.get("diagnosis_rounds", 0)
    steps = state.get("diag_steps", 0)
    if not _use_llm(config):
        _emit(agent, "LLM disabled or unreachable: applying transparent rule engine")
        await _pace(config, 1.0)
        return _rule_fallback(state, rounds, "rules", "LLM not available.")
    if steps >= MAX_DIAG_STEPS:
        return _rule_fallback(state, rounds, "fallback", f"Tool budget of {MAX_DIAG_STEPS} steps exhausted.")

    new_msgs = []
    if steps == 0:
        if rounds == 0:
            new_msgs = [SystemMessage(DIAG_SYSTEM), HumanMessage(_diag_brief(state))]
        else:
            ax = state["spectral"].get("axial") or {}
            new_msgs = [HumanMessage("A follow-up measurement was taken. Updated brief:\n" + _diag_brief(state)
                                     + (f"\nAxial orders (mm/s): {json.dumps(ax.get('orders_mm_s', {}))}" if ax else "")
                                     + "\nRe-evaluate and call submit_diagnosis again.")]
    _emit(agent, "Reasoning over evidence" if steps == 0 else "Reviewing tool results")
    try:
        llm = get_llm().bind_tools(ALL_DIAG_TOOLS)
        ai: AIMessage = await llm.ainvoke(list(state.get("messages", [])) + new_msgs, config)
    except Exception as e:
        return _rule_fallback(state, rounds, "fallback", f"LLM call failed ({type(e).__name__}).")

    out = {"messages": new_msgs + [ai], "diag_steps": steps + 1, "llm_usage": {agent: "live"}}
    calls = [tc["name"] for tc in ai.tool_calls]
    text = ai.content if isinstance(ai.content, str) else " ".join(
        p.get("text", "") for p in ai.content if isinstance(p, dict))
    submit = [tc for tc in ai.tool_calls if tc["name"] == "submit_diagnosis"]
    if submit:
        d = _normalize_diag(submit[0]["args"], rounds, "live")
        tool_msgs = [ToolMessage("Diagnosis recorded." if tc["name"] == "submit_diagnosis"
                                 else "Skipped: diagnosis already submitted.", tool_call_id=tc["id"])
                     for tc in ai.tool_calls]
        out.update(messages=new_msgs + [ai] + tool_msgs, diagnosis=d, diagnosis_rounds=rounds + 1, diag_steps=0)
        out["agent_log"] = [_log(agent, f"Submitted diagnosis: {d['fault_title']} (confidence {d['confidence']}). "
                                        f"{d['rationale']}", "decision")]
    elif calls:
        out["agent_log"] = [_log(agent, (text.strip() + " " if text.strip() else "") + "Calling tools: "
                                 + ", ".join(calls), "llm")]
    else:
        fb = _rule_fallback(state, rounds, "fallback", "LLM answered without submitting.")
        fb["diagnosis"]["rationale"] = text[:600] or fb["diagnosis"]["rationale"]
        out.update({k: v for k, v in fb.items() if k != "llm_usage"})
    return out


def route_after_diagnostician(state: VibState):
    if state.get("diag_steps", 0) == 0:
        return "confidence_gate"
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "diag_tools"
    return "confidence_gate"


# --------------------------------------------------------------------------
# 6. Confidence gate (supervisor): loop back for more data or move on
# --------------------------------------------------------------------------

async def confidence_gate(state: VibState, config: RunnableConfig) -> dict:
    agent = "confidence_gate"
    await _pace(config, 0.4)
    d = state["diagnosis"]
    have_axial = bool(state["spectral"].get("axial"))
    rounds = state.get("diagnosis_rounds", 0)
    if d["primary_fault"] == "healthy":
        route, why = "report", "Diagnostician found no fault. Closing as healthy."
    elif (d["confidence"] < 0.7 and not have_axial and rounds < MAX_DIAG_ROUNDS
          and (d.get("request_measurement") or d["primary_fault"] in ("unbalance", "misalignment"))):
        # Supervisor policy: a low-confidence shaft fault always gets an axial reading,
        # whether or not the diagnostician asked for one.
        if not d.get("request_measurement"):
            d = {**d, "request_measurement": {"location": "same", "direction": "Axial",
                                              "reason": "Supervisor policy: confirm a low-confidence shaft fault with axial data"}}
        route = "acquire_more"
        why = (f"Confidence {d['confidence']} < 0.70 and no axial reading yet "
               f"({d['request_measurement']['reason']}). Looping back to acquisition.")
    else:
        route = "prognosis"
        why = f"Confidence {d['confidence']} accepted for {d['fault_title']}. Proceeding to prognosis."
    out = {"triage": {"route": route, "reason": why}, "agent_log": [_log(agent, why, "decision")]}
    if route == "acquire_more":
        out["pending_measurement"] = {"location": state["request"]["location"], "direction": "Axial",
                                      "purpose": "Follow-up requested by diagnostician: " + d["request_measurement"]["reason"].rstrip(". ")}
    return out


def route_after_gate(state: VibState):
    return {"acquire_more": "acquisition", "prognosis": "prognosis", "report": "report"}[state["triage"]["route"]]


# --------------------------------------------------------------------------
# 7. Prognosis / remaining useful life
# --------------------------------------------------------------------------

BEARING_FAULTS = ("outer_race", "inner_race")


async def prognosis(state: VibState, config: RunnableConfig) -> dict:
    agent = "prognosis"
    d, sev = state["diagnosis"], state["severity"]
    fault = d["primary_fault"]
    level = state["request"]["level"]
    rng = np.random.default_rng(_seed(config["configurable"].get("thread_id"), "trend"))
    _emit(agent, "Pulling 120 days of trend history from the historian")
    await _pace(config, 0.5)
    if fault in BEARING_FAULTS:
        key = "BPFO" if fault == "outer_race" else "BPFI"
        current = state["spectral"]["radial"]["envelope"][key][0]["amp_g"]
        indicator, unit = f"Envelope amplitude at {key}", "gE"
        alert, danger, baseline = 0.25, 0.6, 0.02
    else:
        current = sev["velocity_rms_mm_s"]
        indicator, unit = "Overall velocity RMS", "mm/s"
        alert, danger, baseline = sev["limits"]["B/C"], sev["limits"]["C/D"], 0.8
    onset = {"early": -35, "moderate": -55, "severe": -80}.get(level, -55)
    days = np.arange(-120, 1)
    growth = math.log(max(current, baseline * 1.05) / baseline) / -onset
    y = np.where(days < onset, baseline, baseline * np.exp(growth * (days - onset)))
    y = y * (1 + rng.normal(0, 0.06, len(days)))
    y[-1] = current
    trend = [{"day": int(t), "value": round(float(v), 4)} for t, v in zip(days, y)]

    _emit(agent, "Fitting exponential degradation model to post-onset data")
    await _pace(config, 0.7)
    post = days >= onset
    t, ly = days[post].astype(float), np.log(np.maximum(y[post], 1e-6))
    b, a = (float(v) for v in np.polyfit(t, ly, 1))
    resid = ly - (a + b * t)
    se_b = float(np.sqrt(np.sum(resid ** 2) / max(1, len(t) - 2) / np.sum((t - t.mean()) ** 2)))

    def rul_for(slope):
        if current >= danger:
            return 0.0
        if slope <= 1e-4:
            return None
        return max(0.0, (math.log(danger) - (a + slope * 0)) / slope)

    rul = rul_for(b)
    rul_lo, rul_hi = rul_for(b + 2 * se_b), rul_for(max(1e-5, b - 2 * se_b))
    horizon = int(min(180, (rul or 120) * 1.3 + 10))
    forecast = [{"day": int(t2), "value": round(float(math.exp(a + b * t2)), 4)}
                for t2 in range(0, horizon + 1, max(1, horizon // 60))]
    prog = {
        "indicator": indicator, "unit": unit, "current": round(float(current), 4),
        "alert": alert, "danger": danger, "onset_day": onset,
        "model": f"y = exp({a:.3f} + {b:.4f} t)", "growth_per_day": round(float(b), 4),
        "rul_days": None if rul is None else round(rul, 1),
        "rul_range": [None if rul_lo is None else round(rul_lo, 1), None if rul_hi is None else round(rul_hi, 1)],
        "trend": trend, "forecast": forecast,
    }
    msg = ("Already beyond the danger limit." if rul == 0 else
           "No significant growth trend." if rul is None else
           f"{indicator} {current:.3g} {unit}, growing {b * 100:.1f}%/day. RUL to danger limit ~{rul:.0f} days "
           f"(95% band {prog['rul_range'][0]}-{prog['rul_range'][1]}).")
    return {"prognosis": prog, "agent_log": [_log(agent, msg, "decision")]}


# --------------------------------------------------------------------------
# 8. Maintenance planner: LLM drafts, guardrails enforce policy
# --------------------------------------------------------------------------

class WorkOrderDraft(BaseModel):
    title: str = Field(description="Short work order title")
    priority: Literal["P1", "P2", "P3", "P4"]
    due_within_days: int
    tasks: list[str] = Field(description="Ordered task steps, include isolation/LOTO first")
    parts: list[str]
    estimated_hours: float
    skills: list[str]
    safety: list[str]
    justification: str = Field(description="2-3 sentences linking evidence, severity and RUL to the priority")


PRIORITY_ORDER = ["P1", "P2", "P3", "P4"]


def _policy_priority(state: VibState) -> tuple[str, int, str]:
    zone, rul = state["severity"]["zone"], state["prognosis"].get("rul_days")
    fault = state["diagnosis"]["primary_fault"]
    if zone == "D" or (rul is not None and rul <= 7):
        return "P1", 2, "Zone D or RUL <= 7 days"
    if zone == "C" or (rul is not None and rul <= 30) or fault == "inner_race":
        return "P2", 7, "Zone C, RUL <= 30 days, or inner race defect"
    if rul is not None and rul <= 90:
        return "P3", 30, "RUL <= 90 days"
    return "P4", 60, "No near-term risk"


def _resolve_parts(state: VibState, parts: list[str]) -> list[dict]:
    out, seen = [], set()
    for p in parts:
        name = p
        low = p.lower()
        bearing = state["asset"]["bearing"]["model"]
        known = [k for k in SPARE_PARTS if k.lower() in low]
        if known:
            name = known[0]
        elif "bearing" in low:
            name = bearing
        if name in seen:
            continue
        seen.add(name)
        stock = SPARE_PARTS.get(name)
        out.append({"part": name, **(stock or {"on_hand": None, "location": "Check with stores", "lead_time_days": None})})
    return out


async def planner(state: VibState, config: RunnableConfig) -> dict:
    agent = "planner"
    d, sev, prog, asset = state["diagnosis"], state["severity"], state["prognosis"], state["asset"]
    kb = FAULT_KB[d["primary_fault"]]
    floor, floor_days, floor_reason = _policy_priority(state)
    review = state.get("review") or {}
    revisions = state.get("plan_revisions", 0)
    feedback = review.get("comment") if review.get("decision") == "reject" else None
    mode, draft = "rules", None
    _emit(agent, "Drafting work order" + (" with reviewer feedback" if feedback else ""))
    if _use_llm(config):
        prompt = (
            "You are a maintenance planner for an industrial plant. Draft one corrective work order.\n"
            f"Asset: {json.dumps({k: asset[k] for k in ('id', 'name', 'type', 'site', 'criticality', 'rpm')})}\n"
            f"Diagnosis: {d['fault_title']} (confidence {d['confidence']}). Evidence: {d['evidence']}\n"
            f"Severity: {sev['velocity_rms_mm_s']} mm/s, ISO zone {sev['zone']}.\n"
            f"Prognosis: RUL {prog.get('rul_days')} days on {prog['indicator']}.\n"
            f"Standard actions: {kb['actions']}. Typical parts: {kb['parts']} (bearing model {asset['bearing']['model']}). "
            f"Spare parts stock: {json.dumps(SPARE_PARTS)}. In `parts` use exact catalogue names only.\n"
            f"Maintenance history: {json.dumps(MAINTENANCE_HISTORY.get(asset['id'], []))}\n"
            f"Plant policy: minimum priority {floor} ({floor_reason}), due within {floor_days} days or sooner.\n"
            + (f"The reliability engineer REJECTED the previous draft with this feedback, address it: {feedback}\n"
               if feedback else "")
        )
        try:
            llm = get_llm(0.2).with_structured_output(WorkOrderDraft, method="function_calling")
            draft = (await llm.ainvoke(prompt, config)).model_dump()
            mode = "live"
        except Exception as e:
            mode = "fallback"
            _emit(agent, f"LLM failed ({type(e).__name__}); using planning template")
    if draft is None:
        draft = {
            "title": f"{asset['id']}: {kb['title']} - corrective action",
            "priority": floor, "due_within_days": floor_days,
            "tasks": ["Isolate and lock out motor (LOTO), verify zero energy"] + kb["actions"]
                     + ["Post-maintenance vibration check, confirm Zone A/B"],
            "parts": kb["parts"], "estimated_hours": kb["duration_h"], "skills": kb["skills"],
            "safety": ["LOTO per site procedure", "Guard removal permit", "Rotating equipment hazard"],
            "justification": (f"{kb['title']} with confidence {d['confidence']}; overall {sev['velocity_rms_mm_s']} mm/s "
                              f"(Zone {sev['zone']}); RUL {prog.get('rul_days')} days. Policy: {floor_reason}."),
        }
        if feedback:
            draft["tasks"].insert(1, f"Reviewer requirement: {feedback}")
            draft["justification"] += f" Revised per reviewer: {feedback}"
    guard = None
    if PRIORITY_ORDER.index(draft["priority"]) > PRIORITY_ORDER.index(floor):
        guard = f"Guardrail raised priority {draft['priority']} -> {floor} ({floor_reason})."
        draft["priority"] = floor
    draft["due_within_days"] = min(int(draft["due_within_days"]), floor_days)
    wo = {
        **draft,
        "id": f"WO-{asset['id']}-{(revisions + 1):02d}",
        "asset_id": asset["id"],
        "fault": d["primary_fault"],
        "parts": _resolve_parts(state, draft["parts"]),
        "revision": revisions + 1,
        "mode": mode,
        "guardrail": guard,
        "requires_approval": draft["priority"] in ("P1", "P2"),
    }
    logs = [_log(agent, f"Drafted {wo['id']} rev {wo['revision']}: {wo['priority']}, due in {wo['due_within_days']} days, "
                        f"{len(wo['tasks'])} tasks ({mode}).", "decision")]
    if guard:
        logs.append(_log(agent, guard, "warn"))
    return {"work_order": wo, "plan_revisions": revisions + 1, "llm_usage": {agent: mode}, "agent_log": logs}


def route_after_planner(state: VibState):
    return "human_review" if state["work_order"]["requires_approval"] else "report"


# --------------------------------------------------------------------------
# 9. Human in the loop
# --------------------------------------------------------------------------

async def human_review(state: VibState, config: RunnableConfig) -> dict:
    agent = "human_review"
    wo = state["work_order"]
    # interrupt() pauses the graph here. The checkpoint is saved, the run ends, and the
    # UI shows the approval panel. Command(resume=...) re-enters this node and interrupt()
    # returns the reviewer's answer.
    answer = interrupt({
        "kind": "work_order_approval",
        "question": f"Approve {wo['id']} ({wo['priority']}) for {state['asset']['id']}?",
        "work_order_id": wo["id"],
        "allow_reject": state.get("plan_revisions", 0) < MAX_PLAN_REVISIONS,
    })
    decision = answer.get("decision", "approve")
    review = {"decision": decision, "comment": answer.get("comment", ""), "reviewer": answer.get("reviewer", "Engineer"),
              "at": _now(), "work_order_id": wo["id"]}
    verb = "approved" if decision == "approve" else "rejected"
    return {"review": review,
            "agent_log": [_log(agent, f"{review['reviewer']} {verb} {wo['id']}"
                                      + (f": \"{review['comment']}\"" if review["comment"] else "."), "human")]}


def route_after_review(state: VibState):
    r = state["review"]
    if r["decision"] == "reject" and state.get("plan_revisions", 0) < MAX_PLAN_REVISIONS + 1:
        return "planner"
    return "report"


# --------------------------------------------------------------------------
# 10. Report
# --------------------------------------------------------------------------

async def report(state: VibState, config: RunnableConfig) -> dict:
    agent = "report"
    await _pace(config, 0.5)
    asset = state["asset"]
    sev = state.get("severity")
    d = state.get("diagnosis")
    wo = state.get("work_order")
    review = state.get("review")
    if state.get("signal_quality", {}).get("verdict") == "fail" and not sev:
        status, headline = "inconclusive", "No valid measurement after the retry budget. Dispatch technician to inspect the sensor."
    elif not d or d["primary_fault"] == "healthy":
        status = "healthy"
        headline = f"{asset['id']} is healthy: {sev['velocity_rms_mm_s']} mm/s (Zone {sev['zone']}), no fault signatures."
    elif review and review["decision"] == "reject":
        status, headline = "on_hold", f"{d['fault_title']} confirmed, but {wo['id']} was rejected. Plan on hold."
    else:
        status = "action_required"
        appr = (f", approved by {review['reviewer']}" if review and review["decision"] == "approve"
                else ", auto-approved by policy" if wo and not wo["requires_approval"] else "")
        headline = (f"{d['fault_title']} on {asset['id']} (confidence {d['confidence']}). "
                    f"{wo['id']} issued as {wo['priority']}{appr}.")
    rep = {"status": status, "headline": headline, "generated_at": _now(),
           "path": [e["agent"] for e in state.get("agent_log", [])]}
    return {"report": rep, "agent_log": [_log(agent, headline, "decision")]}
