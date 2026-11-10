"""Asset catalog and fault scenarios for the rotating-machinery demo.

Every asset is a motor-driven machine train with rolling-element bearings.
Bearing geometry is what lets the agents compute defect frequencies, and the
ISO 20816-3 group/foundation pair is what fixes the severity zone limits.
"""
from __future__ import annotations

import math
from copy import deepcopy

# ISO 20816-3 zone boundaries, velocity RMS in mm/s (10-1000 Hz band).
# (group, foundation) -> (A/B, B/C, C/D)
ISO_20816_LIMITS = {
    ("group1", "rigid"): (2.3, 4.5, 7.1),
    ("group1", "flexible"): (3.5, 7.1, 11.0),
    ("group2", "rigid"): (1.4, 2.8, 4.5),
    ("group2", "flexible"): (2.3, 4.5, 7.1),
}

ZONE_TEXT = {
    "A": "Newly commissioned condition",
    "B": "Acceptable for unrestricted long-term operation",
    "C": "Unsatisfactory: limited operation until a suitable opportunity for remedial action",
    "D": "Severe enough to cause damage to the machine",
}

ASSETS = [
    {
        "id": "P-101",
        "name": "Cooling Water Pump P-101",
        "type": "Centrifugal pump, overhung, motor driven",
        "site": "Utilities Unit 1, Cooling Tower Basin",
        "rpm": 1780,
        "power_kw": 75,
        "iso_group": "group2",
        "foundation": "rigid",
        "coupling": "Flexible disc coupling",
        "bearing": {"model": "SKF 6309", "n_balls": 8, "ball_d_mm": 17.46, "pitch_d_mm": 72.5, "contact_deg": 0.0},
        "criticality": "High: single train, no installed spare",
        "measurement_points": ["Motor NDE", "Motor DE", "Pump DE", "Pump NDE"],
    },
    {
        "id": "F-204",
        "name": "Induced Draft Fan F-204",
        "type": "Centrifugal fan, center hung, motor driven",
        "site": "Boiler House, Unit 2",
        "rpm": 1185,
        "power_kw": 250,
        "iso_group": "group2",
        "foundation": "flexible",
        "coupling": "Gear coupling",
        "bearing": {"model": "SKF 22220 E", "n_balls": 19, "ball_d_mm": 25.0, "pitch_d_mm": 145.0, "contact_deg": 9.5},
        "criticality": "High: boiler trips on loss of draft",
        "measurement_points": ["Motor NDE", "Motor DE", "Fan DE", "Fan NDE"],
    },
    {
        "id": "C-310",
        "name": "Process Air Compressor C-310",
        "type": "Screw compressor package, motor driven",
        "site": "Compressor House",
        "rpm": 2975,
        "power_kw": 400,
        "iso_group": "group1",
        "foundation": "rigid",
        "coupling": "Elastomeric jaw coupling",
        "bearing": {"model": "SKF 6316", "n_balls": 8, "ball_d_mm": 34.0, "pitch_d_mm": 130.0, "contact_deg": 0.0},
        "criticality": "Medium: N+1 redundancy with C-311",
        "measurement_points": ["Motor NDE", "Motor DE", "Compressor DE", "Compressor NDE"],
    },
]

SCENARIOS = [
    {"id": "healthy", "label": "Healthy baseline", "fault": "healthy",
     "blurb": "Low 1X, clean spectrum. Should take the healthy fast path."},
    {"id": "unbalance", "label": "Rotor unbalance", "fault": "unbalance",
     "blurb": "Dominant radial 1X with little harmonic content."},
    {"id": "misalignment", "label": "Shaft misalignment", "fault": "misalignment",
     "blurb": "High 1X and 2X. Radial data alone is ambiguous, so the agents should request an axial reading."},
    {"id": "looseness", "label": "Mechanical looseness", "fault": "looseness",
     "blurb": "Long harmonic series, 0.5X subharmonic, raised noise floor."},
    {"id": "outer_race", "label": "Bearing outer race defect", "fault": "outer_race",
     "blurb": "Impacts at BPFO. Barely visible in velocity, obvious in the envelope spectrum."},
    {"id": "inner_race", "label": "Bearing inner race defect", "fault": "inner_race",
     "blurb": "Impacts at BPFI with 1X sidebands from load-zone modulation."},
    {"id": "sensor_fault", "label": "Loose sensor (unbalance underneath)", "fault": "unbalance",
     "sensor_fault_first": True,
     "blurb": "First reading is corrupted by a loose magnet mount. Signal QA should reject it and re-acquire."},
]

SEVERITY_LEVELS = {"early": 0.55, "moderate": 1.0, "severe": 1.6}

MAINTENANCE_HISTORY = {
    "P-101": [
        {"date": "2026-03-14", "type": "PM", "summary": "Coupling inspection and laser alignment. Final offset 0.04 mm, angularity 0.03 mm/100 mm."},
        {"date": "2025-11-02", "type": "CM", "summary": "Replaced pump DE bearing (SKF 6309) after high envelope readings."},
        {"date": "2025-06-20", "type": "PM", "summary": "Impeller cleaned, wear ring clearance within limits."},
    ],
    "F-204": [
        {"date": "2026-05-08", "type": "CM", "summary": "Fan wheel cleaned of ash build-up; trim balanced to 1.1 mm/s."},
        {"date": "2025-12-11", "type": "PM", "summary": "Gear coupling re-greased. Base bolts re-torqued."},
    ],
    "C-310": [
        {"date": "2026-07-22", "type": "PM", "summary": "Motor bearings re-greased, 35 g each side."},
        {"date": "2026-01-15", "type": "PM", "summary": "Coupling element replaced, alignment checked."},
    ],
}

SPARE_PARTS = {
    "SKF 6309": {"on_hand": 2, "location": "Main store, bin B-14", "lead_time_days": 0},
    "SKF 22220 E": {"on_hand": 0, "location": "Vendor", "lead_time_days": 9},
    "SKF 6316": {"on_hand": 1, "location": "Main store, bin B-22", "lead_time_days": 0},
    "Coupling disc pack": {"on_hand": 1, "location": "Main store, bin C-03", "lead_time_days": 0},
    "Shim kit": {"on_hand": 4, "location": "Workshop", "lead_time_days": 0},
    "Balancing weights": {"on_hand": 20, "location": "Workshop", "lead_time_days": 0},
    "Base bolt set": {"on_hand": 3, "location": "Workshop", "lead_time_days": 0},
}


def get_asset(asset_id: str) -> dict:
    for a in ASSETS:
        if a["id"] == asset_id:
            return deepcopy(a)
    raise KeyError(asset_id)


def get_scenario(scenario_id: str) -> dict:
    for s in SCENARIOS:
        if s["id"] == scenario_id:
            return deepcopy(s)
    raise KeyError(scenario_id)


def bearing_frequencies(rpm: float, bearing: dict) -> dict:
    """Classic kinematic bearing defect frequencies in Hz."""
    fr = rpm / 60.0
    n = bearing["n_balls"]
    ratio = bearing["ball_d_mm"] / bearing["pitch_d_mm"] * math.cos(math.radians(bearing["contact_deg"]))
    return {
        "shaft_hz": round(fr, 3),
        "FTF": round(0.5 * fr * (1 - ratio), 3),
        "BSF": round(bearing["pitch_d_mm"] / (2 * bearing["ball_d_mm"]) * fr * (1 - ratio ** 2), 3),
        "BPFO": round(n / 2 * fr * (1 - ratio), 3),
        "BPFI": round(n / 2 * fr * (1 + ratio), 3),
    }


def iso_limits(asset: dict) -> tuple[float, float, float]:
    return ISO_20816_LIMITS[(asset["iso_group"], asset["foundation"])]
