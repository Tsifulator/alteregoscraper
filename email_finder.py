"""Free best-effort contact finder (no paid APIs).

Strategy for a company with a known domain:
  1. Crawl the homepage plus a small set of contact/about/team pages.
  2. Extract emails from mailto links, visible text, and lightly-obfuscated variants.
  3. Prefer role addresses: info / contact / hr / press / epikoinonia.
  4. Pull named people from contact/team/leadership pages when possible.
  5. Fall back to info@domain (the near-universal Greek default).
All results are UNVERIFIED and flagged as such — sanity-check before outreach.
"""
import re
import json
import urllib.request
from collections import deque
from html import unescape
from urllib.parse import urljoin, urlparse

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
MAILTO_RE = re.compile(r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', re.I)
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
# Only treat "at"/"dot" as obfuscation when wrapped in brackets/parens
# (info (at) acme (dot) gr). WITHOUT the brackets, bare "at"/"dot" match
# inside ordinary words ("conversATion" → "convers@ion") and invent fake
# emails out of normal page prose — the source of the gibberish contacts.
OBFUSCATED_EMAIL_RE = re.compile(
    r'([a-zA-Z0-9._%+\-]+)\s*[\(\[\{]\s*at\s*[\)\]\}]\s*'
    r'([a-zA-Z0-9.\-]+)\s*[\(\[\{]\s*(?:dot|\.)\s*[\)\]\}]\s*'
    r'([a-zA-Z]{2,})',
    re.I,
)
TITLE_HINT_RE = re.compile(
    r"\b(CEO|CFO|COO|CTO|GM|Managing Director|Director|Manager|Head|Founder|Owner|"
    r"President|Vice President|Chair|Chairman|Procurement|HR|Human Resources|Finance|"
    r"Accounting|Operations|Commercial|Sales|Marketing|Contact|Contacts|Team|Leadership|"
    r"Διοίκηση|Διεύθυνση|Ομάδα|Προμήθειες|Οικονομικά)\b",
    re.I,
)
NAME_RE = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr|Prof)\.?\s+"
    r"([A-ZΑ-ΩΆ-Ώ][A-Za-zΑ-ΩΆ-Ώά-ώ'’.-]+(?:\s+[A-ZΑ-ΩΆ-Ώ][A-Za-zΑ-ΩΆ-Ώά-ώ'’.-]+){1,2})\b"
    r"|\b([A-ZΑ-ΩΆ-Ώ][A-Za-zΑ-ΩΆ-Ώά-ώ'’.-]+(?:\s+[A-ZΑ-ΩΆ-Ώ][A-Za-zΑ-ΩΆ-Ώά-ώ'’.-]+){1,2})\b"
)

# Common contact-page paths (English + Greek).
CONTACT_PATHS = [
    "",
    "/contact", "/contact-us", "/contactus", "/contact-us/",
    "/epikoinonia", "/epikoinwnia", "/el/epikoinonia", "/epikoinonia/",
    "/about", "/about-us", "/company", "/who-we-are", "/about-us/",
    "/team", "/our-team", "/people", "/leadership", "/management",
    "/executive-team", "/executives", "/staff", "/staff-directory",
    "/press", "/press-room", "/news", "/newsroom", "/media", "/blog",
    "/articles", "/insights", "/board", "/authors", "/profiles",
    "/people/", "/team/", "/leadership/", "/management/", "/διοικηση", "/ομαδα",
]
DISCOVERY_HINTS = (
    "contact", "about", "team", "people", "leadership", "management",
    "staff", "executive", "director", "company", "who-we-are",
    "press", "news", "newsroom", "media", "blog", "article", "insight",
    "profile", "bio", "author", "board", "member", "person", "personnel",
    "epikoinonia", "epikoinwnia", "διοικηση", "ομαδα", "διευθυν", "προμηθει",
)

PROFILE_HINTS = (
    "/author", "/authors", "/profile", "/profiles", "/bio", "/people/",
    "/team/", "/staff/", "/leadership/", "/management/", "/board/",
)

NAME_STOPWORDS = {
    "contact", "contacts", "team", "about", "management", "leadership",
    "director", "managing", "manager", "head", "founder", "owner",
    "president", "chair", "chairman", "chief", "executive", "officer",
    "procurement", "finance", "accounting", "operations", "commercial",
    "sales", "marketing", "human", "resources", "hr",
}

# Preferred local-parts in priority order for B2B facility outreach.
ROLE_PRIORITY = ["info", "contact", "epikoinonia", "hr", "careers", "press",
                 "office", "sales", "facilities", "procurement", "hello"]

# Local-parts that are role addresses, NOT person names.
_ROLE_LOCALS = {
    "info", "contact", "hr", "procurement", "facilities", "facility",
    "sales", "support", "office", "press", "careers", "jobs", "hello",
    "admin", "marketing", "finance", "operations", "ops", "logistics",
    "general", "management", "accounting", "complaints", "noreply",
    "no-reply", "webmaster", "postmaster", "abuse", "security",
    "billing", "legal", "reception", "helpdesk", "service", "team",
    "enquiries", "inquiries", "information", "purchasing", "technical",
    "maintenance", "epikoinonia", "promitheies", "oikonomiko",
}


def name_from_email(email: str) -> str | None:
    """Try to extract a person's name from an email prefix.
    Returns 'First Last' or 'F. Lastname' or None."""
    local = email.split("@")[0].lower()
    if local in _ROLE_LOCALS or any(local.startswith(r) for r in _ROLE_LOCALS):
        return None

    # firstname.lastname@ or firstname_lastname@
    parts = re.split(r"[._]", local)
    if len(parts) == 2:
        first, last = parts
        if len(first) >= 2 and len(last) >= 2 and first.isalpha() and last.isalpha():
            return f"{first.capitalize()} {last.capitalize()}"

    # A single-token local part (george / maria / newsletter / reservations)
    # cannot be reliably split into initial + surname — doing so produced
    # gibberish like "G. Eorge" / "N. Ewsletter". Only the unambiguous
    # first.last / first_last pattern above yields a trustworthy name.
    return None

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
                  "your@", "@email.com", "@yourdomain", "@example", "@domain.",
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


def _html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", html)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"</div\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    # Collapse runs of spaces/tabs but KEEP newlines — _extract_names relies on
    # line structure for its title-context guard. Collapsing newlines made the
    # whole page one line, so a single "Contact"/"Team" anywhere falsely gave
    # every Title-Case phrase on the page name context.
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def _normalize_obfuscations(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"\s+\[at\]\s+|\s+\(at\)\s+|\s+\{at\}\s+", "@", text, flags=re.I)
    text = re.sub(r"\s+\[dot\]\s+|\s+\(dot\)\s+|\s+\{dot\}\s+", ".", text, flags=re.I)
    # NOTE: deliberately do NOT collapse bare " at "/" dot " — replacing those
    # standalone words turns normal prose ("more info at our site") into fake
    # email addresses. Only bracketed obfuscation (above) is safe to normalize.
    return text


def _extract_emails(html: str) -> set[str]:
    found: set[str] = set(m.lower() for m in MAILTO_RE.findall(html))
    found.update(m.lower() for m in EMAIL_RE.findall(html))

    normalized = _normalize_obfuscations(html)
    found.update(m.group(0).lower() for m in EMAIL_RE.finditer(normalized))

    for local, domain, tld in OBFUSCATED_EMAIL_RE.findall(normalized):
        found.add(f"{local}@{domain}.{tld}".lower())
    return found


def _iter_jsonld_objects(html: str):
    for block in re.findall(r'(?is)<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html):
        payload = block.strip()
        if not payload:
            continue
        try:
            data = json.loads(payload)
        except Exception:
            continue
        if isinstance(data, list):
            for item in data:
                yield item
        else:
            yield data


def _extract_structured_contacts(html: str) -> tuple[set[str], dict[str, dict]]:
    emails: set[str] = set()
    people: dict[str, dict] = {}

    def walk(node):
        if isinstance(node, dict):
            node_type = node.get("@type")
            if isinstance(node_type, list):
                node_type = " ".join(str(item) for item in node_type)
            node_type = str(node_type or "")
            name = node.get("name")
            email = node.get("email") or node.get("emailAddress")
            if isinstance(email, str) and email:
                emails.add(email.lower())
            if isinstance(name, str) and name and node_type.lower() in {"person", "organization", "contactpoint"}:
                key = name.lower()
                people.setdefault(key, {"name": name, "email": None, "source": "jsonld"})
                if isinstance(email, str) and email:
                    people[key]["email"] = email.lower()
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for obj in _iter_jsonld_objects(html):
        walk(obj)
    return emails, people


def _looks_like_person_name(text: str) -> bool:
    parts = [part for part in re.split(r"\s+", text.strip()) if part]
    if not 2 <= len(parts) <= 3:
        return False
    if any(part.lower().strip(".,") in NAME_STOPWORDS for part in parts):
        return False
    return all(re.match(r"^[A-ZΑ-ΩΆ-Ώ][A-Za-zΑ-ΩΆ-Ώά-ώ'’.-]+$", part) for part in parts)


def _extract_names(text: str, loose: bool = False) -> set[str]:
    names: set[str] = set()
    lines = [line.strip() for line in re.split(r"[\r\n]+", text) if line.strip()]
    for idx, line in enumerate(lines):
        has_title_context = TITLE_HINT_RE.search(line)
        if not has_title_context:
            if idx > 0 and TITLE_HINT_RE.search(lines[idx - 1]):
                has_title_context = True
            elif idx + 1 < len(lines) and TITLE_HINT_RE.search(lines[idx + 1]):
                has_title_context = True
        if not has_title_context and not loose:
            continue
        for match in NAME_RE.finditer(line):
            name = match.group(1) or match.group(2)
            if not name:
                continue
            cleaned = re.sub(r"\s+", " ", name).strip(" -,;:")
            if len(cleaned.split()) >= 2 and _looks_like_person_name(cleaned):
                names.add(cleaned)
        if loose and _looks_like_person_name(line):
            names.add(line)
    return names


def _is_internal_link(url: str, domain: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return False
    host = parsed.netloc.lower()
    if not host:
        return True
    return host == domain or host.endswith("." + domain) or (domain.startswith("www.") and host == domain[4:])


def _discover_pages(base: str, html: str, domain: str) -> list[str]:
    pages: list[str] = []
    seen: set[str] = set()

    def add_page(url: str) -> None:
        if url not in seen:
            seen.add(url)
            pages.append(url)

    for raw_href in HREF_RE.findall(html):
        href = raw_href.strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        lower_href = href.lower()
        if not any(hint in lower_href for hint in DISCOVERY_HINTS):
            if not any(hint in lower_href for hint in PROFILE_HINTS):
                continue
        url = urljoin(base, href)
        if _is_internal_link(url, domain):
            add_page(url)

    for rel_url in re.findall(r'rel=["\']author["\'][^>]*href=["\']([^"\']+)["\']', html, re.I):
        url = urljoin(base, rel_url.strip())
        if _is_internal_link(url, domain):
            add_page(url)

    for profile_url in re.findall(r'(?i)<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)["\']', html):
        url = profile_url.strip()
        if _is_internal_link(url, domain):
            add_page(url)
    return pages


def _safe_fetch_candidates(domain: str) -> list[tuple[str, str]]:
    base_candidates = [f"https://{domain}", f"https://www.{domain}", f"http://{domain}"]
    seen_urls: set[str] = set()
    queue: deque[str] = deque(base_candidates)
    results: list[tuple[str, str]] = []

    for base in base_candidates[:2]:
        for path in CONTACT_PATHS:
            candidate = urljoin(base.rstrip("/") + "/", path.lstrip("/"))
            if candidate not in queue:
                queue.append(candidate)

    while queue and len(results) < 16:
        url = queue.popleft().rstrip("/")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        html = _fetch(url)
        if not html:
            continue
        results.append((url, html))
        for candidate in _discover_pages(url, html, domain):
            candidate = candidate.rstrip("/")
            if candidate not in seen_urls and candidate not in queue:
                queue.append(candidate)
    return results


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
        return {"email": None, "verified": False, "method": "no-domain", "others": [], "people": []}

    found: set[str] = set()
    people: dict[str, dict] = {}
    pages = _safe_fetch_candidates(domain)
    if not pages:
        pages = [(f"https://{domain}", "")]

    for page_url, html in pages:
        if not html:
            continue
        found.update(_extract_emails(html))
        structured_emails, structured_people = _extract_structured_contacts(html)
        found.update(structured_emails)
        for key, person in structured_people.items():
            existing = people.setdefault(key, person)
            if not existing.get("email") and person.get("email"):
                existing["email"] = person["email"]
            if existing.get("source") == "jsonld":
                existing["source"] = page_url
        text = _html_to_text(html)
        for name in _extract_names(text):
            people.setdefault(name.lower(), {"name": name, "email": None, "source": page_url})

        for email, visible_name in re.findall(r'<a[^>]+href=["\']mailto:([^"\']+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
            email = email.lower().strip()
            visible_text = re.sub(r"<[^>]+>", " ", visible_name)
            visible_text = re.sub(r"\s+", " ", unescape(visible_text)).strip()
            if visible_text:
                matched = _extract_names(visible_text, loose=True)
                if matched:
                    for name in matched:
                        key = name.lower()
                        people.setdefault(key, {"name": name, "email": email, "source": page_url})
                        people[key]["email"] = email
                        people[key]["source"] = page_url
                else:
                    guess = name_from_email(email)
                    if guess:
                        people.setdefault(guess.lower(), {"name": guess, "email": email, "source": page_url})

        if len(found) >= 20 and len(people) >= 4:
            break

    ranked = _clean(found, domain)
    on_domain = [e for e in ranked if e.endswith("@" + domain)]
    people_list = sorted(people.values(), key=lambda p: (0 if p.get("email") else 1, p.get("name", "")))

    if on_domain:
        return {"email": on_domain[0], "verified": False, "method": "scraped",
                "others": on_domain[1:6], "people": people_list}
    if ranked:
        return {"email": ranked[0], "verified": False, "method": "scraped-offdomain",
                "others": ranked[1:6], "people": people_list}
    # Fallback: the Greek-corporate default.
    return {"email": f"info@{domain}", "verified": False, "method": "pattern-guess",
            "others": [f"hr@{domain}", f"contact@{domain}"], "people": people_list}


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
    All emails UNVERIFIED; department addresses are mostly role@domain guesses.
    Also extracts person names from email prefixes and page content where possible."""
    info = find_email(domain)
    info["departments"] = _departments(domain, info)

    # Extract contact names from email prefixes and merge them with page-level names.
    info["contact_names"] = {}
    all_emails = [info["email"]] + info.get("others", [])
    all_emails += [d["email"] for d in info.get("departments", [])]
    for email in all_emails:
        if email:
            name = name_from_email(email)
            if name:
                info["contact_names"][email] = name
    for person in info.get("people", []):
        name = person.get("name")
        email = person.get("email")
        if name and email:
            info["contact_names"][email] = name
    return info


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "dei.gr"
    print(find_email(d))
