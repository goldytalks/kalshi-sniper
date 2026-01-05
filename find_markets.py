"""Find Ravens/Steelers game and AFC North markets"""
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

# Load private key
with open(config["private_key_path"], "rb") as f:
    private_key = serialization.load_pem_private_key(f.read(), password=None)

def sign_request(method: str, path: str, timestamp_ms: int) -> str:
    message = f"{timestamp_ms}{method}{path}".encode()
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
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
        "Content-Type": "application/json"
    }

def api_get(endpoint: str, params: dict = None) -> dict:
    path = f"/trade-api/v2{endpoint}"
    headers = get_headers("GET", path)
    r = requests.get(
        f"https://api.elections.kalshi.com{path}",
        headers=headers,
        params=params or {},
        timeout=30
    )
    return r.json()

# Get all markets and filter
print("Fetching all open markets...")
all_markets = []
cursor = None
pages = 0

while pages < 20:  # Limit to 20 pages
    params = {"limit": 200, "status": "open"}
    if cursor:
        params["cursor"] = cursor

    result = api_get("/markets", params)
    markets = result.get("markets", [])
    all_markets.extend(markets)

    cursor = result.get("cursor")
    pages += 1
    print(f"  Page {pages}: {len(markets)} markets (total: {len(all_markets)})")

    if not cursor or not markets:
        break

print(f"\nTotal markets fetched: {len(all_markets)}")

# Search for relevant markets
keywords = ["ravens", "steelers", "afc north", "baltimore", "pittsburgh", "nfl"]
relevant = []

for m in all_markets:
    title = m.get("title", "").lower()
    ticker = m.get("ticker", "").lower()

    for kw in keywords:
        if kw in title or kw in ticker:
            relevant.append(m)
            break

print(f"\nFound {len(relevant)} relevant markets:")
print("="*80)

for m in relevant:
    ticker = m.get("ticker")
    title = m.get("title")
    yes_bid = m.get("yes_bid")  # Best bid for yes
    yes_ask = m.get("yes_ask")  # Best ask for yes

    print(f"\nTicker: {ticker}")
    print(f"Title: {title}")
    print(f"Yes Bid/Ask: {yes_bid}/{yes_ask}")

    # Get orderbook for more detail
    try:
        ob = api_get(f"/markets/{ticker}/orderbook", {"depth": 5})
        orderbook = ob.get("orderbook", {})
        yes_levels = orderbook.get("yes", [])
        no_levels = orderbook.get("no", [])
        print(f"Orderbook depth - Yes: {len(yes_levels)}, No: {len(no_levels)}")
        if yes_levels:
            print(f"  Top Yes bids: {yes_levels[:3]}")
        if no_levels:
            print(f"  Top No bids: {no_levels[:3]}")
    except Exception as e:
        print(f"Orderbook error: {e}")
