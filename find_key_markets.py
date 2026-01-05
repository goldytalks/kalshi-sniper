"""Find the key markets: Ravens/Steelers ML and AFC North winner"""
import json
import time
import base64
import requests
from pathlib import Path
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

# Get events first - these group related markets
print("="*60)
print("SEARCHING FOR KEY EVENTS")
print("="*60)

events = []
cursor = None
for _ in range(10):
    params = {"limit": 100, "status": "open"}
    if cursor:
        params["cursor"] = cursor
    result = api_get("/events", params)
    events.extend(result.get("events", []))
    cursor = result.get("cursor")
    if not cursor:
        break

print(f"Found {len(events)} total events\n")

# Search for NFL-related events
print("NFL-Related Events:")
print("-"*60)
for e in events:
    title = e.get("title", "").lower()
    ticker = e.get("event_ticker", "")
    if any(kw in title for kw in ["nfl", "ravens", "steelers", "afc", "pittsburgh", "baltimore"]):
        print(f"Event: {ticker}")
        print(f"  Title: {e.get('title')}")
        print(f"  Category: {e.get('category')}")
        print()

# Now search markets for simple moneyline
print("\n" + "="*60)
print("SEARCHING FOR SIMPLE MONEYLINE MARKETS")
print("="*60)

markets = []
cursor = None
for _ in range(30):  # More pages
    params = {"limit": 200, "status": "open"}
    if cursor:
        params["cursor"] = cursor
    result = api_get("/markets", params)
    markets.extend(result.get("markets", []))
    cursor = result.get("cursor")
    if not cursor:
        break
    print(f"  Fetched {len(markets)} markets...")

print(f"\nTotal markets: {len(markets)}")

# Filter for simple moneyline (not parlays)
print("\nLooking for simple moneyline markets (not parlays)...")
for m in markets:
    ticker = m.get("ticker", "")
    title = m.get("title", "")

    # Skip multi-leg markets (parlays)
    if "," in title:
        continue

    title_lower = title.lower()
    if any(kw in title_lower for kw in ["ravens", "steelers", "baltimore", "pittsburgh", "afc north"]):
        yes_bid = m.get("yes_bid", 0)
        yes_ask = m.get("yes_ask", 0)
        print(f"\nTicker: {ticker}")
        print(f"  Title: {title}")
        print(f"  Yes Bid/Ask: {yes_bid}/{yes_ask}")
        print(f"  Last Price: {m.get('last_price')}")
        print(f"  Volume: {m.get('volume')}")
        print(f"  Open Interest: {m.get('open_interest')}")

# Also check for division winner markets
print("\n" + "="*60)
print("SEARCHING FOR DIVISION/CONFERENCE WINNER MARKETS")
print("="*60)

for m in markets:
    title = m.get("title", "")
    ticker = m.get("ticker", "")

    # Skip parlays
    if "," in title:
        continue

    title_lower = title.lower()
    if any(kw in title_lower for kw in ["afc north", "division", "conference", "playoff"]):
        if "nfl" in title_lower or any(team in title_lower for team in ["ravens", "steelers", "bengals", "browns"]):
            yes_bid = m.get("yes_bid", 0)
            yes_ask = m.get("yes_ask", 0)
            print(f"\nTicker: {ticker}")
            print(f"  Title: {title}")
            print(f"  Yes Bid/Ask: {yes_bid}/{yes_ask}")
            print(f"  Last Price: {m.get('last_price')}")
