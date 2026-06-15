"""Persistent record of companies already sent, so leads never repeat."""
import json
import re
from config import SENT_LOG


def _norm(name: str) -> str:
    """Normalize a company name for dedup (lowercase, strip par/punct/extra space)."""
    name = name.lower()
    name = re.sub(r"\(.*?\)", "", name)          # drop parenthetical qualifiers
    name = re.sub(r"[^\w\s]", " ", name, flags=re.UNICODE)
    name = re.sub(r"\b(s\.?a\.?|ae|α\.?ε\.?|group|hellas|greece|ελλάς)\b", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def load_sent() -> set[str]:
    if not SENT_LOG.exists():
        return set()
    try:
        data = json.loads(SENT_LOG.read_text())
        return {_norm(n) for n in data.get("companies", [])}
    except Exception:
        return set()


def already_sent(name: str, sent: set[str]) -> bool:
    return _norm(name) in sent


def record_sent(names: list[str]) -> None:
    """Append newly-sent company names to the log (keeps original display names)."""
    existing = []
    if SENT_LOG.exists():
        try:
            existing = json.loads(SENT_LOG.read_text()).get("companies", [])
        except Exception:
            existing = []
    existing.extend(names)
    SENT_LOG.write_text(json.dumps({"companies": existing}, ensure_ascii=False, indent=2))
