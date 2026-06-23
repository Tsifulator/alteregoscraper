"""Configuration for the ALTER EGO lead scraper."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)
# Sent-log path is overridable so it can live on a Railway persistent volume
# (containers are ephemeral — without this, dedup state resets every run).
SENT_LOG = Path(os.getenv("SENT_LOG_PATH", str(PROJECT_ROOT / "sent_companies.json")))

# --- LLM backend (hybrid) ---
# "auto"   : Ollama if reachable, else Gemini (free), else Claude — same code everywhere.
# "ollama" : force local Ollama.  "gemini": force Google Gemini (free tier).
# "claude" : force the Claude API.
LLM_BACKEND = os.getenv("LLM_BACKEND", "auto").lower()

# --- Ollama (local LLM — free) ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3")

# --- Claude (cloud fallback — cheap; ~$0.003 / lead on Haiku) ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")

# --- Gemini (cloud fallback — small free tier: gemini-2.5-flash is 20 req/day) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# --- Groq (PRIMARY cloud backend — FREE tier: 1,000 req/day, no card) ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# --- Email (Gmail SMTP) ---
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", "tsiflik@bc.edu")
CC_EMAIL = os.getenv("CC_EMAIL", "").strip()   # optional, comma-separated extra recipients

# --- Volume ---
# Twice-daily runs × 5 = 10 fresh companies per day.
COMPANIES_PER_RUN = int(os.getenv("COMPANIES_PER_RUN", "5"))
# How many raw candidates to feed the classifier before giving up on a run.
MAX_CANDIDATES_TO_SCAN = int(os.getenv("MAX_CANDIDATES_TO_SCAN", "40"))

# After crawling a company's site, run one extra LLM pass that reads the scraped
# team/leadership/contact text and names the actual PERSON per target department
# (Procurement, HR, FM, Finance, Mgmt, Ops). One call per company; fail-soft.
LLM_DEPARTMENT_NAMES = os.getenv("LLM_DEPARTMENT_NAMES", "true").lower() == "true"

# If true, write the digest HTML to logs/ instead of emailing (for testing).
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# --- Qualifying criteria (a company must meet AT LEAST ONE; list ALL it meets) ---
CRITERIA = {
    "brand_name": "A recognizable national/multinational brand name (e.g. Mastercard, "
                  "Microsoft, Nike, Coca-Cola) with a presence in Greece. Prestige logo "
                  "= reference value for ALTER EGO.",
    "large_footprint": "Operates large physical facilities in Greece — big m² of offices, "
                       "stores, warehouses/logistics, malls, hospitals, hotels, factories, "
                       "data centers, campuses. The larger the floor area the better.",
    "large_greek_company": "A large Greek company / group (e.g. ΔΕΗ/PPC, OTE, Mytilineos, "
                           "OPAP, Jumbo, the big banks) — major Greek employer or ATHEX-listed.",
    "high_revenue": "High annual revenue / turnover in Greece (rough estimate is fine). "
                    "The larger the revenue the better the lead.",
    "large_workforce": "Large number of employees IN GREECE (rough estimate is fine). More "
                       "employees = more facility/people-services to manage = the better the lead.",
    "high_growth": "A fast-growing / scaling company with strong upward momentum in Greece "
                   "(rapid expansion, new sites or stores, fresh funding/investment, rising "
                   "headcount). May be only mid-sized today but a high-potential FUTURE IFM "
                   "account — worth engaging early.",
}

VALID_CRITERIA = set(CRITERIA.keys())

# --- Location enrichment (Nominatim / OpenStreetMap — free, no key needed) ---
# Always ON. Finds company addresses in Greece via Nominatim.

# --- Greek business-news RSS feeds (fail-soft; bad feeds are skipped) ---
RSS_FEEDS = [
    "https://www.naftemporiki.gr/feed/",
    "https://www.capital.gr/rss/Capital_Epicheiriseis.xml",
    "https://www.insider.gr/rss.xml",
    "https://www.ot.gr/feed/",
    "https://www.businessdaily.gr/feed",
    "https://www.euro2day.gr/rss/companies.xml",
    "https://www.newmoney.gr/feed/",
    "https://www.moneyreview.gr/feed/",
    "https://www.reporter.gr/feed",
    "https://www.powergame.gr/feed/",
]
