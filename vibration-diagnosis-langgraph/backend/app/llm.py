"""LLM access through AvalAI's OpenAI-compatible endpoint, with a health probe."""
from __future__ import annotations

import os
import threading
import time

import httpx
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BASE_URL = os.getenv("AVALAI_BASE_URL", "https://api.avalai.ir/v1")
MODEL = os.getenv("LLM_MODEL", "claude-haiku-5-5")
API_KEY = os.getenv("AVALAI_API_KEY", "")

_status = {"available": None, "checked_at": 0.0, "detail": "not checked"}


def _probe() -> None:
    if not API_KEY:
        _status.update(available=False, detail="AVALAI_API_KEY missing in backend/.env", checked_at=time.time())
        return
    try:
        r = httpx.get(f"{BASE_URL}/models", headers={"Authorization": f"Bearer {API_KEY}"}, timeout=6)
        _status.update(available=r.status_code < 500 and r.status_code != 401, detail=f"HTTP {r.status_code}")
    except Exception as e:  # network down, DNS, TLS ...
        _status.update(available=False, detail=f"{type(e).__name__}: unreachable")
    _status["checked_at"] = time.time()


def _watch() -> None:
    # AvalAI drops out for minutes at a time from this network: re-probe a failure every 15 s,
    # a healthy link every 60 s. Runs in the background so no request waits on a 6 s timeout.
    while True:
        _probe()
        time.sleep(60 if _status["available"] else 15)


threading.Thread(target=_watch, daemon=True, name="llm-probe").start()


def llm_status(force: bool = False) -> dict:
    """Latest probe result; force=True probes now (the UI's re-check button)."""
    if force:
        _probe()
    return dict(_status, model=MODEL)


def get_llm(temperature: float = 0.1) -> ChatOpenAI:
    return ChatOpenAI(model=MODEL, api_key=API_KEY, base_url=BASE_URL, temperature=temperature,
                      timeout=45, max_retries=1, streaming=True)
