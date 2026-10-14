"""
Magis Real Estate watcher — pushes a phone notification when a new
Eindhoven listing appears on https://magisrealestate.com/for-rent

Setup (once):
    pip install requests beautifulsoup4
    Install the free "ntfy" app on your phone and subscribe to NTFY_TOPIC below.

Run:
    python magis_watcher.py          # loops forever, checks every INTERVAL_MIN
    python magis_watcher.py --once   # single check (for Task Scheduler / cron)
    python magis_watcher.py --test   # send a test notification and exit
"""

import json
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ---------------- config ----------------
CITY = "Eindhoven"
INTERVAL_MIN = 10                      # minutes between checks
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "justs-magis-CHANGE-ME")  # GitHub secret, or edit here for local use
BASE = "https://magisrealestate.com"
URL = f"{BASE}/for-rent"
STATE_FILE = Path(__file__).with_name("magis_seen.json")
CITIES = ["Eindhoven", "Tilburg", "Amersfoort", "Rijswijk", "'s-Hertogenbosch", "Den Bosch"]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/129.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
# ----------------------------------------


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def notify(title, message, click_url=URL):
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=message.encode("utf-8"),
            headers={"Title": title, "Click": click_url, "Priority": "high", "Tags": "house"},
            timeout=15,
        )
    except requests.RequestException as e:
        log(f"notification failed: {e}")


def load_seen():
    try:
        return set(json.loads(STATE_FILE.read_text()))
    except (FileNotFoundError, ValueError):
        return set()


def save_seen(seen):
    STATE_FILE.write_text(json.dumps(sorted(seen), indent=1))


def card_text(a):
    """Walk up from a link to the smallest container that mentions a city."""
    node = a
    for _ in range(8):
        node = node.parent
        if node is None:
            break
        text = " ".join(node.get_text(" ").split())
        if len(text) > 1500:
            break
        if any(c.lower() in text.lower() for c in CITIES):
            return text
    return " ".join(a.get_text(" ").split())


def fetch_listings():
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    m = re.search(r"(\d+)\s+available residences?", soup.get_text(" "))
    total = int(m.group(1)) if m else None

    listings = {}
    for a in soup.find_all("a", href=True):
        href = urljoin(BASE, a["href"]).split("?")[0].split("#")[0].rstrip("/")
        path = urlparse(href).path
        # detail pages live under /for-rent/<something>
        if urlparse(href).netloc.endswith("magisrealestate.com") and re.match(r"^/for-rent/.+", path):
            text = card_text(a)
            if CITY.lower() in text.lower():
                listings[href] = text[:200]
    return total, listings


def check(seen):
    total, listings = fetch_listings()
    new = {u: t for u, t in listings.items() if u not in seen}
    log(f"site total available: {total} | {CITY}: {len(listings)} | new: {len(new)}")

    for url, text in new.items():
        notify(f"New Magis listing in {CITY}", text, click_url=url)
        log(f"NEW: {url}  {text}")
    seen.update(new)

    # Fallback: if the site shows available units but no detail links were parsed,
    # the page layout probably changed — alert once so you can check manually.
    if total and not listings and "layout-warning" not in seen:
        notify("Magis: listings online", f"{total} residence(s) available — check the site.")
        seen.add("layout-warning")
    if total == 0:
        seen.discard("layout-warning")

    save_seen(seen)


def main():
    if "--test" in sys.argv:
        notify("Magis watcher", "Test notification works.")
        log("test sent")
        return

    seen = load_seen()
    if "--once" in sys.argv:
        check(seen)
        return

    log(f"watching {URL} for {CITY}, every {INTERVAL_MIN} min (Ctrl+C to stop)")
    while True:
        try:
            check(seen)
        except Exception as e:  # keep running through network hiccups
            log(f"error: {e}")
        time.sleep(INTERVAL_MIN * 60 + random.randint(0, 60))


if __name__ == "__main__":
    main()
