"""Engineering tools the LLM diagnostician can call.

Tools read the graph state through InjectedState, so the LLM never sees or has
to pass around raw data. It only asks engineering questions.
"""
from __future__ import annotations

import json
from typing import Annotated, Literal

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from . import signals as S
from .knowledge import FAULT_IDS, FAULT_KB
from .machines import MAINTENANCE_HISTORY, bearing_frequencies

FaultName = Literal["unbalance", "misalignment", "looseness", "outer_race", "inner_race", "healthy"]


def _valid(state) -> list[dict]:
    rej = set(state.get("rejected", []))
    return [m for m in state.get("measurements", []) if m["id"] not in rej]


@tool
def list_measurements(state: Annotated[dict, InjectedState]) -> str:
    """List the valid vibration measurements taken so far (location, direction, overall velocity RMS)."""
    rows = [{"id": m["id"], "location": m["location"], "direction": m["direction"],
             "velocity_rms_mm_s": m["features"]["velocity_rms_mm_s"], "kurtosis": m["features"]["kurtosis"]}
            for m in _valid(state)]
    return json.dumps(rows)


@tool
def get_order_amplitudes(direction: Literal["radial", "axial"], state: Annotated[dict, InjectedState]) -> str:
    """Velocity amplitudes (mm/s peak) at running-speed orders 0.5X..10X for the radial or axial reading."""
    spec = state.get("spectral", {}).get(direction)
    if not spec:
        return json.dumps({"error": f"No {direction} measurement available. Request one via submit_diagnosis."})
    o = spec["orders_mm_s"]
    return json.dumps({"shaft_hz": spec["shaft_hz"], "orders_mm_s": o,
                       "ratio_2X_1X": round(o["2X"] / o["1X"], 2) if o["1X"] else None,
                       "harmonic_count": spec["harmonic_count"], "noise_floor_mm_s": spec["noise_floor_mm_s"]})


@tool
def get_bearing_defect_frequencies(state: Annotated[dict, InjectedState]) -> str:
    """Kinematic defect frequencies (Hz) for the monitored bearing: FTF, BSF, BPFO, BPFI."""
    a = state["asset"]
    return json.dumps({"bearing": a["bearing"]["model"], **bearing_frequencies(a["rpm"], a["bearing"])})


@tool
def check_envelope_spectrum(defect: Literal["BPFO", "BPFI", "BSF", "FTF"], state: Annotated[dict, InjectedState]) -> str:
    """Envelope (demodulated 2-5 kHz) spectrum amplitude and SNR at 1x-3x the given bearing defect frequency.
    SNR above ~6 is a clear peak. For BPFI also returns the 1X sidebands."""
    spec = state.get("spectral", {}).get("radial")
    if not spec:
        return json.dumps({"error": "no radial measurement"})
    out = {"defect": defect, "harmonics": spec["envelope"][defect]}
    if defect == "BPFI":
        out["sidebands_1X"] = spec["bpfi_sidebands"]
    return json.dumps(out)


@tool
def get_time_statistics(state: Annotated[dict, InjectedState]) -> str:
    """Time-waveform statistics of the latest radial reading: RMS, peak, crest factor, kurtosis."""
    radial = [m for m in _valid(state) if m["direction"] != "Axial"]
    return json.dumps(radial[-1]["features"] if radial else {"error": "no radial reading"})


@tool
def lookup_fault_signature(fault: FaultName) -> str:
    """Return the textbook vibration signature and confirmation checks for a fault type."""
    kb = FAULT_KB[fault]
    return json.dumps({"fault": fault, "signature": kb["signature"], "confirm": kb["confirm"]})


@tool
def get_maintenance_history(state: Annotated[dict, InjectedState]) -> str:
    """Recent maintenance history (CMMS) for this asset."""
    return json.dumps(MAINTENANCE_HISTORY.get(state["asset"]["id"], []))


@tool
def submit_diagnosis(primary_fault: FaultName, confidence: float, evidence: list[str], rationale: str,
                     secondary_faults: list[str] | None = None,
                     request_axial_measurement: bool = False, request_reason: str = "") -> str:
    """Submit the final diagnosis. Call this exactly once when you are done investigating.
    confidence is 0..1. Set request_axial_measurement=true (with request_reason) if an axial reading
    is needed to separate competing hypotheses and none has been taken yet."""
    return "Diagnosis recorded."


INVESTIGATION_TOOLS = [list_measurements, get_order_amplitudes, get_bearing_defect_frequencies,
                       check_envelope_spectrum, get_time_statistics, lookup_fault_signature,
                       get_maintenance_history]
ALL_DIAG_TOOLS = INVESTIGATION_TOOLS + [submit_diagnosis]
assert set(FAULT_IDS) <= set(FaultName.__args__)
