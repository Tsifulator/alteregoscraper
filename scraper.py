"""Sources candidate Greek companies from two places:
  1. Greek business-news RSS  → fresh, topical companies (expansions, new HQs/stores)
  2. Curated seed list        → reliable big Greek caps + multinationals

Returns a shuffled, deduplicated candidate list. Qualification + pitch are done
later by the Ollama classifier; this just gathers raw candidates.
"""
import random

import feedparser

from config import RSS_FEEDS
from seed_companies import SEED_COMPANIES


def _scrape_news(max_items_per_feed: int = 8) -> list[dict]:
    """Pull recent business headlines. Each becomes a 'news' candidate whose
    subject company the classifier will extract + judge."""
    items = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url, request_headers={"User-Agent": "AlterEgoScraper/1.0"})
            for entry in feed.entries[:max_items_per_feed]:
                title = entry.get("title", "").strip()
                summary = entry.get("summary", entry.get("description", "")).strip()
                if not title:
                    continue
                items.append({
                    "source_type": "news",
                    "name": None,                       # classifier extracts the company
                    "headline": title,
                    "context": summary[:400],
                    "link": entry.get("link", ""),
                    "feed": feed.feed.get("title", url),
                })
        except Exception as e:
            print(f"[WARN] feed failed {url}: {e}")
    return items


def _seed_candidates() -> list[dict]:
    cands = []
    for c in SEED_COMPANIES:
        cands.append({
            "source_type": "seed",
            "name": c["name"],
            "domain": c.get("domain"),
            "sector": c.get("sector"),
            "criteria": c.get("criteria", []),
            "note": c.get("note", ""),
        })
    return cands


def gather_candidates() -> list[dict]:
    """Return a shuffled mix of seed + news candidates."""
    seed = _seed_candidates()
    news = _scrape_news()
    random.shuffle(seed)
    random.shuffle(news)
    # Interleave: prefer some fresh news, backed by the reliable seed list.
    mixed = []
    si, ni = 0, 0
    while si < len(seed) or ni < len(news):
        # 2 seed : 1 news ratio (seed is pre-vetted, news is bonus freshness)
        for _ in range(2):
            if si < len(seed):
                mixed.append(seed[si]); si += 1
        if ni < len(news):
            mixed.append(news[ni]); ni += 1
    return mixed


if __name__ == "__main__":
    cands = gather_candidates()
    print(f"Gathered {len(cands)} candidates")
    for c in cands[:15]:
        label = c.get("name") or c.get("headline")
        print(f"  [{c['source_type']}] {label}")
