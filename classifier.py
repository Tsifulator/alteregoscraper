"""Ollama-powered classifier. For each candidate it decides whether the company
qualifies (meets >=1 criterion, is in Greece, isn't an existing client) and writes
the tailored ALTER EGO pitch: why they're a fit + what services to offer."""
import json
import re

from config import CRITERIA, VALID_CRITERIA
from company_brief import ALTER_EGO_BRIEF, EXISTING_CLIENTS
from seed_companies import domain_for_name
import llm


def _extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of an LLM response (handles ``` fences)."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except Exception:
                    return None
    return None


_CRITERIA_TEXT = "\n".join(f'  - "{k}": {v}' for k, v in CRITERIA.items())


def _build_prompt(candidate: dict) -> str:
    if candidate["source_type"] == "seed":
        subject = (
            f'Company: {candidate["name"]}\n'
            f'Sector: {candidate.get("sector", "unknown")}\n'
            f'Known facts: {candidate.get("note", "")}\n'
            f'Pre-identified criteria it meets: {candidate.get("criteria", [])}\n'
            "This company is pre-vetted as Greece-based and qualifying. "
            "Confirm the criteria and focus on writing a sharp, specific pitch."
        )
    else:
        subject = (
            f'Greek business-news headline: "{candidate.get("headline", "")}"\n'
            f'Context: {candidate.get("context", "")}\n'
            "Identify the main COMPANY this is about. Only qualify it if it is a "
            "real company operating in Greece that clearly meets a criterion. If the "
            "headline is about markets/politics/macro with no single qualifying company, "
            "set qualifies=false."
        )

    return f"""You are a B2B lead analyst for ALTER EGO, an Integrated Facility Management company in Greece.

{ALTER_EGO_BRIEF}

A company QUALIFIES as a lead only if it is based/operating IN GREECE and meets AT LEAST ONE of these criteria:
{_CRITERIA_TEXT}

List EVERY criterion the company meets (not just one). Bigger Greek revenue / more Greek employees / more m² in Greece = a better lead.
IMPORTANT: revenue, employee count and floor area must ALL be for the company's GREEK operations ONLY — never global/worldwide totals. Give your best rough estimate of the Greek figures (clearly approximate is fine); if you only know a global figure, estimate just the Greek share.

Do NOT qualify these existing ALTER EGO clients: {sorted(EXISTING_CLIENTS)}.

Evaluate this candidate:
{subject}

Respond with ONLY a JSON object, no prose, in exactly this shape:
{{
  "company": "clean display name",
  "in_greece": true,
  "qualifies": true,
  "criteria_met": ["brand_name", "large_footprint", "large_greek_company", "high_revenue", "large_workforce"],
  "criteria_explanation": "one short sentence on WHY it meets each criterion listed",
  "sector": "short sector label",
  "revenue_estimate": "rough annual revenue IN GREECE only, e.g. '~€80M (Greece, est.)' or 'unknown'",
  "employee_estimate": "rough headcount IN GREECE only, e.g. '~500 in Greece (est.)' or 'unknown'",
  "floor_area_estimate": "rough total m² of their Greek facilities, e.g. '~30,000 m² (est.)' or 'unknown'",
  "why_interest": "1-2 sentences: their likely facility pain points / what would interest them about outsourced IFM",
  "what_we_provide": "1-2 sentences naming the specific ALTER EGO services to pitch them"
}}
criteria_met must be a subset of {sorted(VALID_CRITERIA)} and reflect only criteria actually met."""


def classify_candidate(candidate: dict) -> dict | None:
    """Return an enriched lead dict if it qualifies, else None."""
    try:
        raw = llm.generate(_build_prompt(candidate))
    except Exception as e:
        print(f"[WARN] LLM call failed: {e}")
        return None

    data = _extract_json(raw)
    if not data or not data.get("qualifies") or not data.get("in_greece", True):
        return None

    criteria = [c for c in data.get("criteria_met", []) if c in VALID_CRITERIA]
    if not criteria:
        return None

    company = (data.get("company") or candidate.get("name") or "").strip()
    if not company:
        return None
    # Exclude existing clients: exact match on short codes (ey, bms, snf) +
    # substring match for distinctive multi-word names (catches "Stavros Niarchos
    # Park", "Estée Lauder Hellas", etc. — not just the exact stored string).
    company_norm = company.lower()
    if company_norm in EXISTING_CLIENTS or any(
        " " in c and c in company_norm for c in EXISTING_CLIENTS
    ):
        return None

    # Seed candidates carry their domain; news leads borrow one if we already
    # know the company, so they still get a best-effort contact email.
    domain = candidate.get("domain") or domain_for_name(company)

    return {
        "company": company,
        "criteria_met": criteria,
        "criteria_explanation": data.get("criteria_explanation", ""),
        "sector": data.get("sector") or candidate.get("sector", ""),
        "revenue_estimate": data.get("revenue_estimate", "unknown"),
        "employee_estimate": data.get("employee_estimate", "unknown"),
        "floor_area_estimate": data.get("floor_area_estimate", "unknown"),
        "why_interest": data.get("why_interest", ""),
        "what_we_provide": data.get("what_we_provide", ""),
        "domain": domain,
        "source_type": candidate["source_type"],
        "link": candidate.get("link", ""),
    }
