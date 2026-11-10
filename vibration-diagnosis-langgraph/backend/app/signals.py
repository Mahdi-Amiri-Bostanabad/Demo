"""Synthetic accelerometer data and the signal-processing toolkit the agents use.

Raw waveforms never go into the LangGraph state. They are kept in SIGNAL_STORE
and the state only holds a reference id plus small previews and features.
That keeps checkpoints small, which is the same pattern you would use with a
real historian or blob store.
"""
from __future__ import annotations

import uuid

import numpy as np
from scipy import signal as sps
from scipy.stats import kurtosis

from .machines import SEVERITY_LEVELS, bearing_frequencies

FS = 20480  # Hz
N = 32768   # 1.6 s, 0.625 Hz resolution
G = 9.80665
FULL_SCALE_G = 50.0

SIGNAL_STORE: dict[str, dict] = {}


# --------------------------------------------------------------------------
# Synthesis
# --------------------------------------------------------------------------

def _vel_tone(t, f, v_pk_mm_s, phase=0.0):
    """Acceleration (m/s^2) of a sinusoid whose velocity amplitude is v_pk mm/s."""
    return (v_pk_mm_s / 1000.0) * 2 * np.pi * f * np.sin(2 * np.pi * f * t + phase)


def _impacts(t, rate_hz, amp_g, rng, resonance_hz=3200.0, damping=900.0, modulation=None):
    """Train of decaying resonance ringdowns, the textbook bearing-defect signature."""
    acc = np.zeros_like(t)
    period = 1.0 / rate_hz
    ring_len = int(0.012 * FS)
    tau = np.arange(ring_len) / FS
    ring = np.exp(-damping * tau) * np.sin(2 * np.pi * resonance_hz * tau)
    t0 = rng.uniform(0, period)
    while t0 < t[-1]:
        jitter = rng.normal(0, 0.004 * period)  # slip
        i = int((t0 + jitter) * FS)
        if 0 <= i < len(t):
            a = amp_g * G * (1 + 0.15 * rng.normal())
            if modulation is not None:
                a *= modulation(t0)
            end = min(len(t), i + ring_len)
            acc[i:end] += a * ring[: end - i]
        t0 += period
    return acc


def synthesize(asset: dict, fault: str, level: str, location: str, direction: str,
               seed: int, sensor_fault: bool = False) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(N) / FS
    fr = asset["rpm"] / 60.0
    k = SEVERITY_LEVELS.get(level, 1.0)
    axial = direction == "Axial"
    bf = bearing_frequencies(asset["rpm"], asset["bearing"])

    # Healthy machine baseline: small 1X, smaller 2X, vane/blade pass, broadband noise.
    acc = _vel_tone(t, fr, 0.9 if not axial else 0.5, rng.uniform(0, 6.28))
    acc += _vel_tone(t, 2 * fr, 0.25, rng.uniform(0, 6.28))
    acc += _vel_tone(t, 6 * fr, 0.35, rng.uniform(0, 6.28))  # vane pass
    acc += rng.normal(0, 0.02 * G, N)

    if fault == "unbalance":
        acc += _vel_tone(t, fr, (5.2 if not axial else 0.6) * k, 0.3)
        acc += _vel_tone(t, 2 * fr, 0.25 * k, 1.1)
    elif fault == "misalignment":
        if axial:
            acc += _vel_tone(t, fr, 3.4 * k, 0.2)
            acc += _vel_tone(t, 2 * fr, 3.0 * k, 0.9)
            acc += _vel_tone(t, 3 * fr, 1.1 * k, 0.4)
        else:
            acc += _vel_tone(t, fr, 3.4 * k, 0.2)
            acc += _vel_tone(t, 2 * fr, 1.9 * k, 0.9)
    elif fault == "looseness":
        for h in range(1, 11):
            acc += _vel_tone(t, h * fr, (3.0 / h ** 0.6) * k * (0.4 if axial else 1.0), rng.uniform(0, 6.28))
        for h in (0.5, 1.5, 2.5):
            acc += _vel_tone(t, h * fr, 0.9 * k, rng.uniform(0, 6.28))
        acc += rng.normal(0, 0.05 * G * k, N)
    elif fault == "outer_race":
        acc += _impacts(t, bf["BPFO"], 2.2 * k, rng)
        acc += _vel_tone(t, fr, 0.6 * k, 0.1)
    elif fault == "inner_race":
        mod = lambda tt: 0.55 + 0.45 * np.cos(2 * np.pi * fr * tt)  # load zone
        acc += _impacts(t, bf["BPFI"], 2.6 * k, rng, resonance_hz=3600, modulation=mod)
        acc += _vel_tone(t, fr, 0.8 * k, 0.1)

    if sensor_fault:
        # Loose magnet mount: low-frequency ski slope, rattling spikes and clipping.
        drift = np.cumsum(rng.normal(0, 0.9, N))
        drift = sps.lfilter([1], [1, -0.995], drift) * 0.05 * G
        acc = acc * 0.35 + drift
        spikes = rng.random(N) < 0.002
        acc[spikes] += rng.choice([-1, 1], spikes.sum()) * 80 * G
    acc = np.clip(acc, -FULL_SCALE_G * G, FULL_SCALE_G * G)
    return acc


def acquire(asset: dict, fault: str, level: str, location: str, direction: str,
            seed: int, sensor_fault: bool = False) -> str:
    acc = synthesize(asset, fault, level, location, direction, seed, sensor_fault)
    ref = f"sig_{uuid.uuid4().hex[:10]}"
    SIGNAL_STORE[ref] = {"acc": acc, "fs": FS, "rpm": asset["rpm"]}
    return ref


# --------------------------------------------------------------------------
# Processing
# --------------------------------------------------------------------------

def _spectrum(x: np.ndarray, fs: int):
    w = np.hanning(len(x))
    X = np.fft.rfft(x * w)
    f = np.fft.rfftfreq(len(x), 1 / fs)
    amp = 2 * np.abs(X) / w.sum()  # peak amplitude
    return f, amp


def velocity_spectrum(ref: str):
    s = SIGNAL_STORE[ref]
    f, a = _spectrum(s["acc"], s["fs"])  # m/s^2 peak
    v = np.zeros_like(a)
    nz = f > 0
    v[nz] = a[nz] / (2 * np.pi * f[nz]) * 1000.0  # mm/s peak
    return f, v


def velocity_rms(ref: str, f_lo=10.0, f_hi=1000.0) -> float:
    f, v = velocity_spectrum(ref)
    band = (f >= f_lo) & (f <= f_hi)
    # Hann window ENBW = 1.5 bins; sum of squared peak amplitudes / 2 / 1.5
    return float(np.sqrt(np.sum(v[band] ** 2) / 2 / 1.5))


def envelope_spectrum(ref: str, band=(2000.0, 5000.0), f_max=500.0):
    s = SIGNAL_STORE[ref]
    sos = sps.butter(4, band, btype="bandpass", fs=s["fs"], output="sos")
    xb = sps.sosfiltfilt(sos, s["acc"])
    env = np.abs(sps.hilbert(xb))
    env = env - env.mean()
    f, a = _spectrum(env / G, s["fs"])
    keep = f <= f_max
    return f[keep], a[keep]


def amp_at(f: np.ndarray, a: np.ndarray, target: float, tol_hz: float = 1.5) -> tuple[float, float]:
    m = (f >= target - tol_hz) & (f <= target + tol_hz)
    if not m.any():
        return 0.0, target
    i = np.argmax(np.where(m, a, -1))
    return float(a[i]), float(f[i])


def time_features(ref: str) -> dict:
    x = SIGNAL_STORE[ref]["acc"] / G
    rms = float(np.sqrt(np.mean(x ** 2)))
    pk = float(np.max(np.abs(x)))
    return {
        "accel_rms_g": round(rms, 4),
        "accel_peak_g": round(pk, 3),
        "crest_factor": round(pk / rms if rms else 0.0, 2),
        "kurtosis": round(float(kurtosis(x, fisher=False)), 2),
    }


def quality_checks(ref: str) -> list[dict]:
    x = SIGNAL_STORE[ref]["acc"] / G
    fs = SIGNAL_STORE[ref]["fs"]
    checks = []
    clip_frac = float(np.mean(np.abs(x) >= FULL_SCALE_G * 0.999))
    checks.append({"name": "Clipping", "value": f"{clip_frac*100:.3f}% of samples at full scale",
                   "ok": bool(clip_frac < 0.0005)})
    std = float(np.std(x))
    checks.append({"name": "Sensor alive", "value": f"std {std:.4f} g", "ok": bool(std > 0.005)})
    # Ski slope: energy below 5 Hz relative to total
    f, a = _spectrum(x, fs)
    lf = float(np.sum(a[(f > 0) & (f < 5)] ** 2))
    tot = float(np.sum(a[f > 0] ** 2)) or 1.0
    checks.append({"name": "Ski slope (<5 Hz energy)", "value": f"{lf/tot*100:.1f}% of energy",
                   "ok": bool(lf / tot < 0.25)})
    dc = float(abs(np.mean(x)))
    checks.append({"name": "DC offset", "value": f"{dc:.3f} g", "ok": bool(dc < 0.5)})
    # Mount rattle produces isolated huge spikes; bearing impacts are a few g.
    spikes = int(np.sum(np.abs(x) > 0.6 * FULL_SCALE_G))
    checks.append({"name": "Mount rattle spikes (>30 g)", "value": f"{spikes} samples", "ok": bool(spikes < 5)})
    return checks


def _downsample(xs, ys, n):
    if len(xs) <= n:
        return [round(float(v), 3) for v in xs], [round(float(v), 4) for v in ys]
    # max-preserving decimation so peaks survive
    idx = np.linspace(0, len(xs), n + 1).astype(int)
    ox, oy = [], []
    for i0, i1 in zip(idx[:-1], idx[1:]):
        j = i0 + int(np.argmax(ys[i0:i1]))
        ox.append(round(float(xs[j]), 3))
        oy.append(round(float(ys[j]), 4))
    return ox, oy


def previews(ref: str) -> dict:
    s = SIGNAL_STORE[ref]
    x = s["acc"] / G
    n_wf = int(0.25 * s["fs"])
    step = 6
    wf_t = (np.arange(0, n_wf, step) / s["fs"] * 1000).round(2).tolist()
    wf_y = x[:n_wf:step].round(4).tolist()
    f, v = velocity_spectrum(ref)
    keep = f <= 1000
    sf, sv = _downsample(f[keep], v[keep], 1600)
    ef, ea = envelope_spectrum(ref)
    ef2, ea2 = _downsample(ef, ea, 800)
    return {
        "waveform": {"t_ms": wf_t, "g": wf_y},
        "spectrum": {"f": sf, "v": sv, "unit": "mm/s pk"},
        "envelope": {"f": ef2, "a": ea2, "unit": "g pk"},
    }


def spectral_features(ref: str, asset: dict) -> dict:
    fr = asset["rpm"] / 60.0
    f, v = velocity_spectrum(ref)
    orders = {}
    for h in [0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 9, 10]:
        amp, _ = amp_at(f, v, h * fr, tol_hz=max(1.5, 0.01 * h * fr))
        orders[f"{h:g}X"] = round(amp, 3)
    band = (f > 10) & (f < 1000)
    noise_floor = float(np.median(v[band]))
    ef, ea = envelope_spectrum(ref)
    env_floor = float(np.median(ea[ef > 5])) + 1e-9
    bf = bearing_frequencies(asset["rpm"], asset["bearing"])
    env = {}
    for key in ("FTF", "BSF", "BPFO", "BPFI"):
        harmonics = []
        for h in (1, 2, 3):
            amp, at = amp_at(ef, ea, h * bf[key], tol_hz=max(1.5, 0.012 * h * bf[key]))
            harmonics.append({"h": h, "freq_hz": round(at, 2), "amp_g": round(amp, 4),
                              "snr": round(amp / env_floor, 1)})
        env[key] = harmonics
    # 1X sidebands around BPFI in envelope (inner race modulation)
    sb = []
    for side in (-1, 1):
        amp, at = amp_at(ef, ea, bf["BPFI"] + side * fr, tol_hz=1.5)
        sb.append({"freq_hz": round(at, 2), "snr": round(amp / env_floor, 1)})
    # top spectral peaks for the UI / LLM
    peaks_idx, _ = sps.find_peaks(v[band], height=max(noise_floor * 8, 0.15), distance=8)
    fb, vb = f[band], v[band]
    order = np.argsort(vb[peaks_idx])[::-1][:8]
    top = [{"freq_hz": round(float(fb[peaks_idx[i]]), 2),
            "order": round(float(fb[peaks_idx[i]] / fr), 2),
            "amp_mm_s": round(float(vb[peaks_idx[i]]), 3)} for i in order]
    harmonic_count = sum(1 for h in range(2, 11) if orders[f"{h}X"] > max(0.35, 6 * noise_floor))
    return {
        "shaft_hz": round(fr, 3),
        "orders_mm_s": orders,
        "noise_floor_mm_s": round(noise_floor, 4),
        "harmonic_count": harmonic_count,
        "top_peaks": top,
        "bearing_freqs_hz": bf,
        "envelope": env,
        "envelope_floor_g": round(env_floor, 5),
        "bpfi_sidebands": sb,
    }
