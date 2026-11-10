"""Fault knowledge base and the rule-based hypothesis engine.

The rules are deliberately transparent. The spectral agent uses them to produce
ranked candidate hypotheses (a prior), the LLM diagnostician then verifies the
candidates with tools, and if the LLM is unavailable the rules alone produce the
diagnosis. Either way the evidence trail is explicit.
"""
from __future__ import annotations

FAULT_KB = {
    "unbalance": {
        "title": "Rotor unbalance",
        "signature": "Dominant 1X in radial directions, sinusoidal waveform, low 2X/1X (<0.3), low axial 1X, phase difference ~90 deg between horizontal and vertical.",
        "confirm": "Compare radial vs axial 1X; check 1X phase stability; inspect for build-up or lost balance weights.",
        "actions": ["Inspect rotor for deposits or erosion and clean", "Field balance in one or two planes to ISO 21940-11 grade G6.3", "Verify after balancing: 1X below 1.5 mm/s"],
        "parts": ["Balancing weights"],
        "duration_h": 6,
        "skills": ["Vibration analyst (Cat II+)", "Mechanical technician"],
    },
    "misalignment": {
        "title": "Shaft misalignment",
        "signature": "High 2X relative to 1X (2X/1X > 0.5), high axial vibration (axial 1X or 2X > 50% of radial), 180 deg axial phase across coupling.",
        "confirm": "Take an axial measurement; check axial 1X and 2X; check coupling condition and soft foot.",
        "actions": ["Check and correct soft foot", "Laser align motor to driven machine within coupling tolerance", "Inspect coupling elements for wear", "Check pipe strain on pump flanges"],
        "parts": ["Shim kit", "Coupling disc pack"],
        "duration_h": 5,
        "skills": ["Millwright", "Laser alignment technician"],
    },
    "looseness": {
        "title": "Mechanical looseness",
        "signature": "Long series of 1X harmonics (often to 10X), half-order subharmonics (0.5X, 1.5X), raised noise floor, truncated waveform.",
        "confirm": "Check harmonic count and 0.5X; inspect base bolts, bearing housing fits and grout.",
        "actions": ["Inspect and re-torque base and bearing housing bolts", "Check grout and baseplate for cracks", "Check bearing fit on shaft and in housing"],
        "parts": ["Base bolt set"],
        "duration_h": 4,
        "skills": ["Mechanical technician"],
    },
    "outer_race": {
        "title": "Rolling bearing outer race defect",
        "signature": "Envelope spectrum peaks at BPFO and harmonics, no 1X sidebands. High kurtosis and crest factor; velocity often still low in early stages.",
        "confirm": "Check envelope at 1-3x BPFO; trend kurtosis; listen with stethoscope.",
        "actions": ["Plan bearing replacement at next opportunity", "Increase monitoring to weekly envelope readings", "Check lubrication condition and quantity", "Inspect removed bearing for root cause (fatigue, contamination, false brinelling)"],
        "parts": ["bearing"],
        "duration_h": 8,
        "skills": ["Mechanical technician", "Vibration analyst (Cat II+)"],
    },
    "inner_race": {
        "title": "Rolling bearing inner race defect",
        "signature": "Envelope peaks at BPFI and harmonics with 1X sidebands (load zone modulation). Typically progresses faster than outer race defects.",
        "confirm": "Check envelope at BPFI and BPFI +/- 1X; trend kurtosis.",
        "actions": ["Replace bearing urgently", "Check shaft fit and housing bore", "Review lubrication interval and grease type", "Inspect removed bearing for root cause"],
        "parts": ["bearing"],
        "duration_h": 8,
        "skills": ["Mechanical technician", "Vibration analyst (Cat II+)"],
    },
    "healthy": {
        "title": "No significant fault",
        "signature": "Low overall velocity, no dominant fault frequencies, envelope spectrum flat.",
        "confirm": "Continue routine monitoring.",
        "actions": ["Continue routine route-based monitoring at the normal interval"],
        "parts": [],
        "duration_h": 0,
        "skills": [],
    },
}

FAULT_IDS = [k for k in FAULT_KB if k != "healthy"]


def rule_hypotheses(spec: dict, time_feats: dict, axial_spec: dict | None) -> list[dict]:
    """Score every fault 0..1 from the extracted features. Returns sorted list."""
    o = spec["orders_mm_s"]
    one, two = o["1X"], o["2X"]
    ratio = two / one if one > 0 else 0.0
    env = spec["envelope"]
    bpfo = max(h["snr"] for h in env["BPFO"])
    bpfi = max(h["snr"] for h in env["BPFI"])
    bpfo_h = sum(1 for h in env["BPFO"] if h["snr"] > 6)
    bpfi_h = sum(1 for h in env["BPFI"] if h["snr"] > 6)
    sb = min(s["snr"] for s in spec["bpfi_sidebands"])
    kurt = time_feats["kurtosis"]
    hc = spec["harmonic_count"]
    half = o["0.5X"]
    out = []

    # Unbalance
    s, ev = 0.0, []
    if one > 2.0:
        s += 0.45; ev.append(f"Radial 1X is high at {one:.2f} mm/s")
    if ratio < 0.3 and one > 1.5:
        s += 0.3; ev.append(f"2X/1X ratio low ({ratio:.2f})")
    if hc <= 1:
        s += 0.1; ev.append("No harmonic series")
    if axial_spec is not None:
        a1 = axial_spec["orders_mm_s"]["1X"]
        if a1 < 0.5 * one:
            s += 0.15; ev.append(f"Axial 1X low ({a1:.2f} mm/s) relative to radial")
        else:
            s -= 0.3; ev.append(f"Axial 1X high ({a1:.2f} mm/s), argues against pure unbalance")
    out.append({"fault": "unbalance", "score": s, "evidence": ev})

    # Misalignment
    s, ev = 0.0, []
    if ratio > 0.4 and one > 1.0:
        s += 0.4; ev.append(f"2X/1X ratio elevated ({ratio:.2f})")
    if one > 1.5:
        s += 0.15; ev.append(f"1X elevated ({one:.2f} mm/s)")
    if axial_spec is None:
        if ratio > 0.4:
            ev.append("No axial reading yet: cannot separate misalignment from unbalance with confidence")
    else:
        a1, a2 = axial_spec["orders_mm_s"]["1X"], axial_spec["orders_mm_s"]["2X"]
        if max(a1, a2) > 0.5 * one:
            s += 0.4; ev.append(f"Axial 1X {a1:.2f} / 2X {a2:.2f} mm/s, high relative to radial")
        else:
            s -= 0.2; ev.append("Axial vibration low")
    if hc > 5:
        s -= 0.2
    out.append({"fault": "misalignment", "score": s, "evidence": ev})

    # Looseness
    s, ev = 0.0, []
    if hc >= 5:
        s += 0.5; ev.append(f"{hc} running-speed harmonics above threshold")
    if half > 0.4:
        s += 0.3; ev.append(f"0.5X subharmonic present ({half:.2f} mm/s)")
    if spec["noise_floor_mm_s"] > 0.02:
        s += 0.1; ev.append("Raised spectral noise floor")
    out.append({"fault": "looseness", "score": s, "evidence": ev})

    # Outer race
    s, ev = 0.0, []
    if bpfo > 8:
        s += 0.5; ev.append(f"Envelope peak at BPFO, SNR {bpfo:.0f}")
    if bpfo_h >= 2:
        s += 0.2; ev.append(f"{bpfo_h} BPFO harmonics in envelope")
    if kurt > 4:
        s += 0.15; ev.append(f"Kurtosis {kurt:.1f} indicates impacting")
    if bpfo > 8 and sb < 6:
        s += 0.1; ev.append("No 1X sidebands, consistent with stationary outer race")
    out.append({"fault": "outer_race", "score": s, "evidence": ev})

    # Inner race
    s, ev = 0.0, []
    if bpfi > 8:
        s += 0.5; ev.append(f"Envelope peak at BPFI, SNR {bpfi:.0f}")
    if bpfi_h >= 2:
        s += 0.15; ev.append(f"{bpfi_h} BPFI harmonics in envelope")
    if sb > 6 and bpfi > 8:
        s += 0.2; ev.append("1X sidebands around BPFI (load-zone modulation)")
    if kurt > 4:
        s += 0.1; ev.append(f"Kurtosis {kurt:.1f} indicates impacting")
    out.append({"fault": "inner_race", "score": s, "evidence": ev})

    for h in out:
        h["score"] = round(max(0.0, min(0.97, h["score"])), 2)
    out.sort(key=lambda h: h["score"], reverse=True)
    return out


def rule_diagnosis(hyps: list[dict], have_axial: bool) -> dict:
    top = hyps[0]
    if top["score"] < 0.35:
        return {"primary_fault": "healthy", "confidence": 0.8, "evidence": ["No fault rule scored above 0.35"],
                "rationale": "Features do not match any fault signature strongly.", "secondary_faults": [],
                "request_measurement": None}
    conf = top["score"]
    req = None
    second = hyps[1]
    ambiguous = (top["fault"] in ("unbalance", "misalignment")
                 and second["fault"] in ("unbalance", "misalignment")
                 and second["score"] >= 0.3 and top["score"] - second["score"] < 0.3)
    if ambiguous and not have_axial:
        conf = min(conf, 0.55)
        req = {"location": "same", "direction": "Axial",
               "reason": "Separate misalignment from unbalance: misalignment shows strong axial 1X/2X."}
    return {
        "primary_fault": top["fault"],
        "confidence": round(conf, 2),
        "evidence": top["evidence"],
        "rationale": f"Rule engine: {FAULT_KB[top['fault']]['signature']}",
        "secondary_faults": [h["fault"] for h in hyps[1:3] if h["score"] >= 0.35],
        "request_measurement": req,
    }
