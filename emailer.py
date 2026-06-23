"""Builds and sends the ALTER EGO daily lead digest via Gmail SMTP."""
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import GMAIL_ADDRESS, GMAIL_APP_PASSWORD, RECIPIENT_EMAIL, CC_EMAIL, DRY_RUN, LOGS_DIR

CRITERIA_LABEL = {
    "brand_name": ("BRAND NAME", "badge-brand"),
    "large_footprint": ("LARGE FOOTPRINT", "badge-foot"),
    "large_greek_company": ("LARGE GREEK CO.", "badge-greek"),
    "high_revenue": ("HIGH REVENUE", "badge-rev"),
    "large_workforce": ("BIG WORKFORCE", "badge-work"),
    "high_growth": ("HIGH GROWTH", "badge-growth"),
}

EMAIL_TEMPLATE = """<!DOCTYPE html>
<html><head><style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin:0; padding:20px; background:#eef1f4; }}
  .container {{ max-width:660px; margin:0 auto; background:#fff; border-radius:12px; overflow:hidden; box-shadow:0 2px 10px rgba(0,0,0,0.08); }}
  .header {{ background:linear-gradient(135deg,#0b2e4f,#114b7d); color:#fff; padding:26px 30px; }}
  .header h1 {{ margin:0; font-size:21px; font-weight:700; letter-spacing:.3px; }}
  .header p {{ margin:6px 0 0; opacity:.85; font-size:13px; }}
  .content {{ padding:20px 30px; }}
  .lead {{ border:1px solid #e6e9ee; border-radius:10px; padding:16px 18px; margin:14px 0; }}
  .lead h2 {{ margin:0 0 6px; font-size:17px; }}
  .lead h2 a {{ color:#0b2e4f; text-decoration:none; }}
  .sector {{ color:#7a8694; font-size:12px; margin:0 0 10px; text-transform:uppercase; letter-spacing:.4px; }}
  .badges {{ margin:0 0 12px; }}
  .badge {{ display:inline-block; font-size:10px; font-weight:700; letter-spacing:.5px; padding:3px 8px; border-radius:5px; margin-right:6px; }}
  .badge-brand {{ background:#e8f0fe; color:#1a56c4; }}
  .badge-foot  {{ background:#fff1e0; color:#c1610b; }}
  .badge-greek {{ background:#e6f6ec; color:#1f7a45; }}
  .badge-rev   {{ background:#f3e9fb; color:#7b2cbf; }}
  .badge-work  {{ background:#fde9ef; color:#c2185b; }}
  .badge-growth {{ background:#e6faf3; color:#0f9d6b; }}
  .stats {{ display:flex; gap:8px; flex-wrap:wrap; margin:10px 0; }}
  .stat {{ background:#f6f8fa; border:1px solid #e6e9ee; border-radius:7px; padding:6px 10px; font-size:12px; color:#33414f; }}
  .stat b {{ display:block; color:#7a8694; font-size:10px; text-transform:uppercase; letter-spacing:.4px; font-weight:700; }}
  .row {{ font-size:13.5px; line-height:1.5; margin:7px 0; color:#33414f; }}
  .row b {{ color:#0b2e4f; }}
  .why {{ color:#475a6b; }}
  .offer {{ color:#114b7d; }}
  .contact {{ background:#f6f8fa; border-radius:7px; padding:9px 12px; font-size:13px; margin-top:10px; }}
  .contact a {{ color:#1a56c4; text-decoration:none; }}
  .unverified {{ color:#b06a00; font-size:11px; font-style:italic; }}
    .people {{ margin-top:8px; padding-top:8px; border-top:1px dashed #e6e9ee; font-size:12.5px; color:#33414f; }}
    .people b {{ color:#0b2e4f; }}
  .depts {{ margin-top:10px; border-top:1px dashed #e6e9ee; padding-top:9px; }}
  .depts-h {{ font-size:10px; font-weight:700; color:#7a8694; text-transform:uppercase; letter-spacing:.4px; margin:0 0 6px; }}
  .dept {{ font-size:12.5px; line-height:1.5; margin:2px 0; color:#33414f; }}
  .dept b {{ display:inline-block; min-width:150px; color:#0b2e4f; }}
  .dept a {{ color:#1a56c4; text-decoration:none; }}
  .dept-person {{ color:#0b2e4f; font-weight:600; }}
  .footer {{ padding:16px 30px; background:#fafbfc; text-align:center; font-size:11.5px; color:#9aa6b2; }}
</style></head><body>
<div class="container">
  <div class="header">
    <h1>ALTER EGO — Daily Lead Digest</h1>
    <p>{timestamp} · {count} Greek companies that fit our criteria</p>
  </div>
  <div class="content">{body}</div>
  <div class="footer">
    Each lead meets ≥1 criterion: recognizable brand, large Greek footprint, major or high-growth Greek company, high Greek revenue, or big workforce.<br>
    All figures are estimates for GREEK operations only. Department contacts are best-effort — names are scraped from the company site where found, otherwise role@domain guesses; all unverified, confirm before outreach. · Curated via Ollama / Groq.
  </div>
</div></body></html>"""

LEAD_BLOCK = """<div class="lead">
  <h2>{name_html}</h2>
  <p class="sector">{sector}</p>
  <div class="badges">{badges}</div>
  <div class="stats">{stats}</div>
  {locations_html}
  <p class="row why"><b>Why they fit:</b> {criteria_explanation}</p>
  <p class="row why"><b>What would interest them:</b> {why_interest}</p>
  <p class="row offer"><b>What we'd provide:</b> {what_we_provide}</p>
  <div class="contact">✉️ <b>Contact:</b> {contact_html}</div>
    {people_html}
  {depts_html}
</div>"""


def _badges(criteria: list[str]) -> str:
    out = ""
    for c in criteria:
        label, cls = CRITERIA_LABEL.get(c, (c.upper(), "badge-brand"))
        out += f'<span class="badge {cls}">{label}</span>'
    return out


def _stats(lead: dict) -> str:
    """Revenue / employees / m² estimate tiles (+ Maps address if enriched)."""
    tiles = [
        ("Revenue · Greece (est.)", lead.get("revenue_estimate", "unknown")),
        ("Employees · Greece (est.)", lead.get("employee_estimate", "unknown")),
        ("Floor area · Greece (est.)", lead.get("floor_area_estimate", "unknown")),
    ]
    if lead.get("osm_floor_m2"):
        tiles.append(("Floor area (OSM measured)", lead["osm_floor_m2"]))
    elif lead.get("osm_footprint_m2"):
        tiles.append(("Footprint (OSM measured)", lead["osm_footprint_m2"]))
    if lead.get("maps_locations"):
        tiles.append(("Locations (Maps)", str(lead["maps_locations"])))
    if lead.get("maps_address"):
        tiles.append(("HQ address (Maps)", lead["maps_address"]))
    out = ""
    for label, val in tiles:
        if val and str(val).lower() != "unknown":
            out += f'<span class="stat"><b>{label}</b>{val}</span>'
    return out


def _contact_html(lead: dict) -> str:
    email = lead.get("email")
    method = lead.get("method", "")
    if not email:
        return '<span class="unverified">no email found — look up manually</span>'
    note = {"scraped": "found on site", "scraped-offdomain": "found on site",
            "pattern-guess": "guessed pattern — verify"}.get(method, method)
    others = lead.get("email_others") or []
    extra = f' · alts: {", ".join(others)}' if others else ""
    return (f'<a href="mailto:{email}">{email}</a> '
            f'<span class="unverified">({note}){extra}</span>')


def _people_html(lead: dict) -> str:
    people = lead.get("contact_people") or []
    if not people:
        return ""
    rows = []
    seen = set()
    for person in people:
        name = (person.get("name") or "").strip()
        email = (person.get("email") or "").strip()
        # Only show people backed by a real email. Bare names scraped from page
        # text are too noisy (nav/marketing phrases like "Accessibility Statement")
        # and were rendering as junk "people found".
        if not name or not email or name.lower() in seen:
            continue
        seen.add(name.lower())
        rows.append(f'<div><b>{name}</b> <a href="mailto:{email}">{email}</a></div>')
    if not rows:
        return ""
    return '<div class="people"><b>People found:</b>' + "".join(rows) + "</div>"


_DEPT_NOTE = {
    "scraped-llm": "name + email found on site",
    "scraped-llm-name": "name found on site · email is a guess",
    "scraped": "found on site",
}


def _departments_html(lead: dict) -> str:
    """Per-department best-effort contacts (Procurement, HR, FM, Finance, etc.).
    Shows the actual person when the LLM found one on the company's site."""
    depts = lead.get("departments") or []
    if not depts:
        return ""
    rows = ""
    for d in depts:
        note = _DEPT_NOTE.get(d.get("method", ""), "guess — verify")
        name = (d.get("name") or "").strip()
        title = (d.get("title") or "").strip()
        person_html = ""
        if name:
            who = f"{name} — {title}" if title else name
            person_html = f'<span class="dept-person">{who}</span> · '
        rows += (f'<div class="dept"><b>{d["dept"]}</b>'
                 f'{person_html}<a href="mailto:{d["email"]}">{d["email"]}</a> '
                 f'<span class="unverified">({note})</span></div>')
    return f'<div class="depts"><div class="depts-h">🎯 Target departments</div>{rows}</div>'


def _locations_html(lead: dict) -> str:
    """Greek locations with addresses from Google Maps."""
    addresses = lead.get("maps_all_addresses") or []
    if not addresses:
        return ""
    count = len(addresses)
    heading = f"📍 Greek locations ({count})"
    rows = "".join(
        f'<div class="dept">{i}. {addr}</div>'
        for i, addr in enumerate(addresses, 1)
    )
    return (f'<div class="depts"><div class="depts-h">{heading}</div>{rows}</div>')


def _name_html(lead: dict) -> str:
    domain = lead.get("domain")
    name = lead["company"]
    if domain:
        return f'<a href="https://{domain}">{name}</a>'
    if lead.get("link"):
        return f'<a href="{lead["link"]}">{name}</a>'
    return name


def build_html(leads: list[dict]) -> str:
    body = ""
    for lead in leads:
        body += LEAD_BLOCK.format(
            name_html=_name_html(lead),
            sector=lead.get("sector", ""),
            badges=_badges(lead.get("criteria_met", [])),
            stats=_stats(lead),
            locations_html=_locations_html(lead),
            criteria_explanation=lead.get("criteria_explanation", ""),
            why_interest=lead.get("why_interest", ""),
            what_we_provide=lead.get("what_we_provide", ""),
            contact_html=_contact_html(lead),
            people_html=_people_html(lead),
            depts_html=_departments_html(lead),
        )
    return EMAIL_TEMPLATE.format(
        timestamp=datetime.now().strftime("%B %d, %Y · %I:%M %p"),
        count=len(leads),
        body=body,
    )


def send_digest(leads: list[dict]) -> None:
    html = build_html(leads)
    subject = f"🎯 ALTER EGO Leads: {len(leads)} Greek companies — {datetime.now().strftime('%b %d, %I:%M %p')}"

    if DRY_RUN:
        out = LOGS_DIR / f"digest-preview-{datetime.now().strftime('%Y%m%d-%H%M%S')}.html"
        out.write_text(html)
        print(f"[DRY_RUN] Digest NOT sent. Preview written to {out}")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = RECIPIENT_EMAIL
    recipients = [RECIPIENT_EMAIL]
    if CC_EMAIL:
        msg["Cc"] = CC_EMAIL
        recipients += [e.strip() for e in CC_EMAIL.split(",") if e.strip()]
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, recipients, msg.as_string())
    print(f"[OK] Digest sent to {RECIPIENT_EMAIL}" + (f" (cc: {CC_EMAIL})" if CC_EMAIL else ""))
