"""Hybrid LLM backend: local Ollama (free) or a cloud API (Gemini / Claude).

The classifier calls generate(prompt) and doesn't care which model answers.
Selection is controlled by LLM_BACKEND:

  - "auto"   (default): Ollama if reachable, else Gemini (free), else Claude.
                        → free Ollama on your laptop, free Gemini in GitHub Actions.
  - "ollama" : always local Ollama.
  - "gemini" : always the Google Gemini API (free tier; needs GEMINI_API_KEY).
  - "claude" : always the Claude API (needs ANTHROPIC_API_KEY).

The backend is resolved once per process and reused for every call.
"""
import json
import urllib.request

from config import (
    LLM_BACKEND,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
)

_resolved: str | None = None
_anthropic_client = None


# --- Ollama ------------------------------------------------------------------
def _ollama_available(timeout: int = 2) -> bool:
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _ollama_generate(prompt: str, timeout: int = 120) -> str:
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read()).get("response", "")


# --- Claude ------------------------------------------------------------------
def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic  # lazy: only needed when the Claude backend is used
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY or None)
    return _anthropic_client


def _claude_generate(prompt: str) -> str:
    # Plain single-shot classification — no thinking/effort (unsupported on Haiku),
    # JSON is parsed downstream exactly as for the Ollama path. max_tokens=1024
    # comfortably covers the ~300-token JSON reply.
    resp = _get_anthropic().messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in resp.content if b.type == "text")


# --- Gemini (free tier: ~1,500 req/day, no card) -----------------------------
def _gemini_generate(prompt: str) -> str:
    import requests  # already a dependency
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent")
    r = requests.post(
        url,
        params={"key": GEMINI_API_KEY},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1024},
        },
        timeout=60,
    )
    r.raise_for_status()
    parts = r.json()["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


# --- Dispatch ----------------------------------------------------------------
def active_backend() -> str:
    """Resolve (once) which backend to use, printing the choice on first call."""
    global _resolved
    if _resolved:
        return _resolved

    if LLM_BACKEND == "ollama":
        _resolved = "ollama"
    elif LLM_BACKEND == "gemini":
        if not GEMINI_API_KEY:
            raise RuntimeError("LLM_BACKEND=gemini but GEMINI_API_KEY is unset.")
        _resolved = "gemini"
    elif LLM_BACKEND == "claude":
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("LLM_BACKEND=claude but ANTHROPIC_API_KEY is unset.")
        _resolved = "claude"
    else:  # auto: free local Ollama first, then free Gemini, then paid Claude
        if _ollama_available():
            _resolved = "ollama"
        elif GEMINI_API_KEY:
            _resolved = "gemini"
        elif ANTHROPIC_API_KEY:
            _resolved = "claude"
        else:
            raise RuntimeError(
                "No LLM backend available: Ollama unreachable and no GEMINI_API_KEY / "
                "ANTHROPIC_API_KEY set. Start Ollama, or set one of those keys."
            )

    detail = {"ollama": OLLAMA_MODEL, "gemini": GEMINI_MODEL,
              "claude": ANTHROPIC_MODEL}[_resolved]
    print(f"  LLM backend: {_resolved} ({detail})")
    return _resolved


def generate(prompt: str) -> str:
    """Return the model's raw text response from the active backend."""
    b = active_backend()
    if b == "ollama":
        return _ollama_generate(prompt)
    if b == "gemini":
        return _gemini_generate(prompt)
    return _claude_generate(prompt)
