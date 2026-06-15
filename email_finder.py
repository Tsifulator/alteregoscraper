"""Free best-effort contact-email finder (no paid APIs).

Strategy for a company with a known domain:
  1. Fetch the homepage + common contact/about pages.
  2. Regex out any published email address (prefer mailto: links).
  3. Prefer role addresses: info / contact / hr / press / epikoinonia.
  4. Fall back to info@domain (the near-universal Greek default).
All results are UNVERIFIED and flagged as such — sanity-check before outreach.
"""
import re
import urllib.request

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
MAILTO_RE = re.compile(r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', re.I)

# Common contact-page paths (English + Greek).
CONTACT_PATHS = ["", "/contact", "/contact-us", "/contactus", "/epikoinonia",
                 "/epikoinwnia", "/el/epikoinonia", "/about", "/about-us", "/company"]

# Preferred local-parts in priority order for B2B facility outreach.
ROLE_PRIORITY = ["info", "contact", "epikoinonia", "hr", "careers", "press",
                 "office", "sales", "facilities", "procurement", "hello"]

# Departments ALTER EGO wants to reach. For each, role local-parts (EN+GR) we
# try to match against scraped on-domain addresses, else guess role@domain.
DEPARTMENTS = [
    ("Procurement",         ["procurement", "purchasing", "supplies", "promitheies"]),
    ("HR",                  ["hr", "careers", "jobs", "recruitment"]),
    ("Facility Management", ["facilities", "facility", "maintenance", "technical"]),
    ("Finance",             ["finance", "accounting", "accounts", "oikonomiko"]),
    ("General Management",  ["office", "management", "info"]),
    ("Operations",          ["operations", "ops", "logistics"]),
]

BAD_SUBSTRINGS = ("example.", "sentry.", "wixpress.", "@2x", ".png", ".jpg",
                  ".svg", ".gif", "@sentry", "godaddy", "domain.com",
                  # template / placeholder addresses that aren't real contacts
                  "your-name", "yourname", "your.name", "your_name", "yourcompany",
                  "your-email", "youremail", "your.email", "your_email",
                  "firstname", "lastname", "first.last", "name.surname",
                  "john.doe", "jane.doe", "johndoe", "janedoe",
                  "@email.com", "@yourdomain", "@example", "@domain.",
                  "@company.com", "@test.", "@mydomain",
                  "noreply", "no-reply", "donotreply", "do-not-reply")


def _fetch(url: str, timeout: int = 8) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 AlterEgoScraper/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read(600_000).decode(charset, errors="ignore")
    except Exception:
        return ""


def _clean(emails: set[str], domain: str) -> list[str]:
    out = []
    for e in emails:
        el = e.lower()
        if any(b in el for b in BAD_SUBSTRINGS):
            continue
        if len(el) > 60:
            continue
        out.append(el)
    # Prefer addresses on the company's own domain, then by role priority.
    def score(e: str) -> int:
        local = e.split("@")[0]
        s = 100 if domain and e.endswith("@" + domain) else 0
        for i, role in enumerate(ROLE_PRIORITY):
            if local == role or local.startswith(role):
                s += (len(ROLE_PRIORITY) - i)
                break
        return s
    return sorted(set(out), key=score, reverse=True)


def find_email(domain: str | None) -> dict:
    """Return {'email': str|None, 'verified': False, 'method': str, 'others': [...]}."""
    if not domain:
        return {"email": None, "verified": False, "method": "no-domain", "others": []}

    found: set[str] = set()
    base = f"https://{domain}"
    for path in CONTACT_PATHS:
        html = _fetch(base + path)
        if not html:
            continue
        found.update(m.lower() for m in MAILTO_RE.findall(html))
        found.update(m.lower() for m in EMAIL_RE.findall(html))
        if len(found) >= 8:
            break

    ranked = _clean(found, domain)
    on_domain = [e for e in ranked if e.endswith("@" + domain)]

    if on_domain:
        return {"email": on_domain[0], "verified": False, "method": "scraped",
                "others": on_domain[1:4]}
    if ranked:
        return {"email": ranked[0], "verified": False, "method": "scraped-offdomain",
                "others": ranked[1:4]}
    # Fallback: the Greek-corporate default.
    return {"email": f"info@{domain}", "verified": False, "method": "pattern-guess",
            "others": [f"hr@{domain}", f"contact@{domain}"]}


def _departments(domain: str | None, info: dict) -> list[dict]:
    """Best-effort email per target department: a scraped on-domain address whose
    role matches the department if we found one, else a role@domain GUESS."""
    if not domain:
        return []
    seen = [e for e in ([info.get("email")] + info.get("others", []))
            if e and e.endswith("@" + domain)]
    out = []
    for dept, roles in DEPARTMENTS:
        local_of = lambda e: e.split("@")[0]
        hit = next((e for e in seen
                    if any(local_of(e) == r or local_of(e).startswith(r) for r in roles)), None)
        if hit:
            out.append({"dept": dept, "email": hit, "method": "scraped"})
        else:
            out.append({"dept": dept, "email": f"{roles[0]}@{domain}", "method": "guess"})
    return out


def find_contacts(domain: str | None) -> dict:
    """find_email(...) plus a 'departments' list — one best-effort email per
    target department (Procurement, HR, Facility Management, Finance, etc.).
    All emails UNVERIFIED; department addresses are mostly role@domain guesses."""
    info = find_email(domain)
    info["departments"] = _departments(domain, info)
    return info


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "dei.gr"
    print(find_email(d))
