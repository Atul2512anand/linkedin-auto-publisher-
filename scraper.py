import html
import json
import os
import random
import re
import sys
from calendar import timegm
from datetime import date, datetime, timezone

import feedparser
import requests

from common import BASE_DIR, LOGS_DIR, load_env

FEEDS = {
    "TechCrunch": "https://techcrunch.com/feed/",
    "Wired": "https://www.wired.com/feed/rss",
    "The Verge": "https://www.theverge.com/rss/index.xml",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/index",
    "Engadget": "https://www.engadget.com/rss.xml",
    "CNET": "https://www.cnet.com/rss/news/",
    "Gizmodo": "https://gizmodo.com/feed",
    "ZDNet": "https://www.zdnet.com/news/rss.xml",
    "Mashable": "https://mashable.com/feed",
    "The Hacker News": "https://thehackernews.com/feeds/posts/default",
    "BleepingComputer": "https://www.bleepingcomputer.com/feed/",
    "SecurityWeek": "https://www.securityweek.com/feed/",
    "KrebsOnSecurity": "https://krebsonsecurity.com/feed/",
    "Hacker News": "https://hnrss.org/frontpage",
}

MIRROR_FEEDS = {
    "BleepingComputer": "https://news.google.com/rss/search?q=site:bleepingcomputer.com+when:3d&hl=en-US&gl=US&ceid=US:en",
    "SecurityWeek": "https://news.google.com/rss/search?q=site:securityweek.com+when:3d&hl=en-US&gl=US&ceid=US:en",
    "KrebsOnSecurity": "https://news.google.com/rss/search?q=site:krebsonsecurity.com+when:3d&hl=en-US&gl=US&ceid=US:en",
}

KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "llm", "chatbot", "openai", "anthropic",
    "cybersecurity", "cyber", "security", "hack", "hacker", "breach", "ransomware", "malware",
    "phishing", "password", "encryption", "privacy", "data leak", "zero-day", "vpn",
    "chip", "semiconductor", "quantum", "cloud", "software", "hardware", "developer", "coding",
    "programmer", "open source", "linux", "windows", "android", "ios", "iphone", "google",
    "microsoft", "nvidia", "meta", "amazon", "startup", "robot", "gpu", "cpu", "browser",
    "internet", "blockchain", "healthcare ai", "hospital", "patient data", "medical device",
]

NEGATIVE_KEYWORDS = [
    "deal", "deals", "discount", "sale", "coupon", "price drop", "best price",
    "buying guide", "black friday", "review:", "hands-on:",
]

EVENT_KEYWORDS = [
    "launch", "launched", "unveil", "unveiled", "announce", "announced", "release", "released",
    "leak", "leaked", "breach", "breached", "hack", "hacked", "hacking", "stolen", "exposed",
    "shut down", "lawsuit", "sues", "banned", "acquires", "acquisition", "record", "outage",
    "exploit", "vulnerability", "patch", "arrested", "fined", "first", "debuts", "reveals",
]

CACHE_DIR = os.path.join(BASE_DIR, "cache")
USED_LINKS_FILE = os.path.join(LOGS_DIR, "used_links.txt")


def clean_text(raw):
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:400]


def entry_datetime(entry):
    stamp = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not stamp:
        return None
    return datetime.fromtimestamp(timegm(stamp), tz=timezone.utc)


def matches_niche(title, summary):
    blob = f"{title} {summary}".lower()
    if any(re.search(rf"\b{re.escape(k)}\b", blob) for k in NEGATIVE_KEYWORDS):
        return False
    if re.search(r"save \$?\d+|\$\d+ off|%\s?off|lowest.?ever", blob):
        return False
    return any(re.search(rf"\b{re.escape(k)}\b", blob) for k in KEYWORDS)


def score_item(item, now):
    score = 0
    if item["age_hours"] is not None:
        if item["age_hours"] <= 12:
            score += 4
        elif item["age_hours"] <= 24:
            score += 3
        elif item["age_hours"] <= 48:
            score += 2
        elif item["age_hours"] <= 72:
            score += 1
    blob = f"{item['title']} {item['summary']}".lower()
    hits = sum(1 for k in EVENT_KEYWORDS if re.search(rf"\b{re.escape(k)}\b", blob))
    score += min(hits * 2, 6)
    return score


def _parse_feed(url):
    resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return feedparser.parse(resp.text)


def collect(max_per_source=10):
    load_env()
    now = datetime.now(timezone.utc)
    max_age = float(os.environ.get("NEWS_MAX_AGE_HOURS", "72"))
    items = []
    seen_links = set()
    for name, url in FEEDS.items():
        via_mirror = False
        try:
            parsed = _parse_feed(url)
        except Exception as exc:
            mirror = MIRROR_FEEDS.get(name)
            if not mirror:
                print(f"WARNING: {name} feed failed: {exc}")
                continue
            try:
                parsed = _parse_feed(mirror)
                via_mirror = True
                print(f"NOTE: {name} direct feed blocked - using Google News mirror")
            except Exception as exc2:
                print(f"WARNING: {name} feed failed even via mirror: {exc2}")
                continue
        count = 0
        for entry in parsed.entries:
            if count >= max_per_source:
                break
            title = clean_text(getattr(entry, "title", ""))
            if via_mirror and title:
                title = re.sub(rf"\s+-\s+{re.escape(name)}.*$", "", title, flags=re.I).strip()
            link = getattr(entry, "link", "")
            summary = clean_text(getattr(entry, "summary", "") or getattr(entry, "description", ""))
            if not title or not link or link in seen_links:
                continue
            if not matches_niche(title, summary):
                continue
            seen_links.add(link)
            published_at = entry_datetime(entry)
            age_hours = ((now - published_at).total_seconds() / 3600) if published_at else None
            if age_hours is not None and age_hours > max_age:
                continue
            items.append({
                "source": name,
                "title": title,
                "link": link,
                "summary": summary,
                "published": published_at.isoformat() if published_at else None,
                "age_hours": round(age_hours, 1) if age_hours is not None else None,
                "score": 0,
            })
            count += 1
    for item in items:
        item["score"] = score_item(item, now)
    items.sort(key=lambda x: x["score"], reverse=True)
    return items


def cache_path():
    return os.path.join(CACHE_DIR, f"news_{date.today().isoformat()}.json")


def get_news_items():
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = cache_path()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    items = collect()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)
    return items


def load_used_links():
    if not os.path.exists(USED_LINKS_FILE):
        return set()
    with open(USED_LINKS_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def mark_used(link):
    os.makedirs(LOGS_DIR, exist_ok=True)
    with open(USED_LINKS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{link}\n")


def pick_news_item():
    items = get_news_items()
    if not items:
        return None
    used = load_used_links()
    fresh = [i for i in items if i["link"] not in used]
    pool = fresh if fresh else items[len(items) // 2:]
    top = pool[: min(len(pool), 8)]
    return random.choice(top)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    news = get_news_items()
    print(f"Collected {len(news)} event candidates (top 10 by freshness/event-score):")
    for item in news[:10]:
        age = f"{item['age_hours']}h ago" if item['age_hours'] is not None else "unknown"
        print(f"- [{item['source']}] ({age}, score {item['score']}) {item['title']}")
