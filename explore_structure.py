"""Explore Kalshi's market structure to understand what's available"""
import json
import time
import base64
import requests
from pathlib import Path
from collections import defaultdict
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# Load config
config_path = Path.home() / ".kalshi" / "config.json"
with open(config_path) as f:
    config = json.load(f)

api_key_id = config["api_key_id"]

with open(config["private_key_path"], "rb") as f:
    private_key = serialization.load_pem_private_key(f.read(), password=None)

def sign_request(method: str, path: str, timestamp_ms: int) -> str:
    message = f"{timestamp_ms}{method}{path}".encode()
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode()

def get_headers(method: str, path: str) -> dict:
    timestamp_ms = int(time.time() * 1000)
    signature = sign_request(method, path, timestamp_ms)
    return {
        "KALSHI-ACCESS-KEY": api_key_id,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": str(timestamp_ms),
    }

def api_get(endpoint: str, params: dict = None) -> dict:
    path = f"/trade-api/v2{endpoint}"
    headers = get_headers("GET", path)
    r = requests.get(f"https://api.elections.kalshi.com{path}", headers=headers, params=params or {}, timeout=30)
    return r.json()

# Sample some markets to understand the structure
print("Sampling markets to understand Kalshi's structure...")
print("="*70)

result = api_get("/markets", {"limit": 100, "status": "open"})
markets = result.get("markets", [])

# Categorize by ticker prefix
prefixes = defaultdict(list)
for m in markets:
    ticker = m.get("ticker", "")
    if "-" in ticker:
        prefix = ticker.split("-")[0]
    else:
        prefix = ticker[:10]
    prefixes[prefix].append(m)

print(f"\nFound {len(prefixes)} ticker prefixes:\n")
for prefix, mlist in sorted(prefixes.items()):
    print(f"{prefix}: {len(mlist)} markets")
    if len(mlist) <= 3:
        for m in mlist:
            print(f"    {m['ticker']}: {m.get('title', '')[:50]}")

# Now look specifically at sports events
print("\n" + "="*70)
print("Looking at Sports category events...")
print("="*70)

result = api_get("/events", {"limit": 200, "status": "open"})
events = result.get("events", [])

sports_events = [e for e in events if e.get("category") == "Sports"]
print(f"\nFound {len(sports_events)} sports events")

# Group by sub-category
subcats = defaultdict(list)
for e in sports_events:
    subcat = e.get("sub_title", "") or e.get("series_ticker", "") or "Unknown"
    subcats[subcat[:30]].append(e)

print("\nSports subcategories:")
for subcat, elist in sorted(subcats.items()):
    print(f"\n{subcat}: {len(elist)} events")
    for e in elist[:5]:
        print(f"    {e.get('event_ticker')}: {e.get('title', '')[:50]}")

# Look at a specific NFL-related event in detail
print("\n" + "="*70)
print("Looking for NFL single game events...")
print("="*70)

for e in events:
    ticker = e.get("event_ticker", "")
    title = e.get("title", "")
    if "NFLSINGLEGAME" in ticker or "nfl" in title.lower():
        print(f"\nEvent: {ticker}")
        print(f"  Title: {title}")
        print(f"  Category: {e.get('category')}")
        print(f"  Sub-title: {e.get('sub_title')}")

        # Get this event's markets
        event_detail = api_get(f"/events/{ticker}")
        event_markets = event_detail.get("markets", [])
        print(f"  Markets in this event: {len(event_markets)}")

        for m in event_markets[:5]:
            print(f"    - {m.get('ticker')}: {m.get('title', '')[:60]}")
        break

# Check what series exist
print("\n" + "="*70)
print("Looking at series (groupings of events)...")
print("="*70)

result = api_get("/series", {"limit": 50})
series = result.get("series", [])

for s in series:
    title = s.get("title", "")
    ticker = s.get("ticker", "")
    if any(kw in title.lower() for kw in ["nfl", "football", "sports", "afc", "nfc"]):
        print(f"\nSeries: {ticker}")
        print(f"  Title: {title}")
        print(f"  Category: {s.get('category')}")
