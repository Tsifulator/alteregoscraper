#!/usr/bin/env python3
"""ALTER EGO lead scraper — finds Greek companies that fit our IFM criteria,
finds a contact email, writes a tailored pitch, and emails a digest.

Runs twice a day (08:00 & 18:00 Athens) → 5 fresh, never-repeated leads each."""
import sys
import traceback
from datetime import datetime

from config import COMPANIES_PER_RUN, MAX_CANDIDATES_TO_SCAN, DRY_RUN
from scraper import gather_candidates
from classifier import classify_candidate
from email_finder import find_contacts
from maps_enrich import enrich as maps_enrich
from overpass_enrich import enrich as overpass_enrich
from emailer import send_digest
from sent_log import load_sent, record_sent, already_sent, _norm


def run():
    print(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] ALTER EGO lead scraper running...")

    sent = load_sent()                 # companies emailed on previous runs
    print(f"  {len(sent)} companies already in sent-log (won't repeat)")

    candidates = gather_candidates()
    print(f"  Gathered {len(candidates)} candidates; scanning up to {MAX_CANDIDATES_TO_SCAN}")

    leads: list[dict] = []
    this_run: set[str] = set()         # guards against duplicates within THIS digest
    scanned = 0

    for cand in candidates:
        if len(leads) >= COMPANIES_PER_RUN or scanned >= MAX_CANDIDATES_TO_SCAN:
            break

        # Cheap pre-skip for seed candidates we've already sent (no LLM call wasted).
        pre_name = cand.get("name")
        if pre_name and (already_sent(pre_name, sent) or _norm(pre_name) in this_run):
            continue

        scanned += 1
        lead = classify_candidate(cand)
        if not lead:
            continue

        key = _norm(lead["company"])
        if key in sent or key in this_run:     # dedup: across runs AND within this digest
            print(f"    ↳ skip duplicate: {lead['company']}")
            continue

        # Best-effort contact email + per-department targets.
        info = find_contacts(lead.get("domain"))
        lead["email"] = info["email"]
        lead["method"] = info["method"]
        lead["email_others"] = info["others"]
        lead["departments"] = info["departments"]
        lead["contact_people"] = info.get("people", [])
        lead["contact_names"] = info.get("contact_names", {})

        # Optional enrichment.
        lead.update(maps_enrich(lead["company"]))           # Nominatim (free, always on)
        lead.update(overpass_enrich(lead["company"]))       # USE_OVERPASS=true

        leads.append(lead)
        this_run.add(key)
        print(f"  ✓ [{len(leads)}/{COMPANIES_PER_RUN}] {lead['company']} "
              f"({', '.join(lead['criteria_met'])}) → {lead['email']}")

    if not leads:
        print("  No qualifying new leads this run — nothing to send.")
        return

    send_digest(leads)
    if DRY_RUN:
        # Preview-only run: don't burn real leads from the permanent sent-log.
        print(f"  [DRY_RUN] {len(leads)} leads previewed — NOT recorded to sent-log.")
    else:
        record_sent([l["company"] for l in leads])
        print(f"  Done — {len(leads)} leads sent & recorded.")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
