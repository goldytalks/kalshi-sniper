"""Check AFC North and NFL Game series specifically"""
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

# Check the AFC North series
print("="*70)
print("AFC NORTH WINNER MARKETS")
print("="*70)

result = api_get("/markets", {"series_ticker": "KXNFLAFCNORTH", "limit": 50})
markets = result.get("markets", [])
print(f"Found {len(markets)} markets in KXNFLAFCNORTH series\n")

for m in markets:
    ticker = m.get("ticker")
    title = m.get("title")
    status = m.get("status")
    yes_bid = m.get("yes_bid")
    yes_ask = m.get("yes_ask")
    last_price = m.get("last_price")
    volume = m.get("volume")

    print(f"Ticker: {ticker}")
    print(f"  Title: {title}")
    print(f"  Status: {status}")
    print(f"  Yes Bid/Ask: {yes_bid}/{yes_ask}")
    print(f"  Last Price: {last_price}")
    print(f"  Volume: {volume}")

    # Get orderbook
    if status == "open":
        ob = api_get(f"/markets/{ticker}/orderbook", {"depth": 5})
        orderbook = ob.get("orderbook", {})
        print(f"  Orderbook: {orderbook}")
    print()

# Check the NFL Game series
print("="*70)
print("NFL SINGLE GAME MARKETS (KXNFLGAME)")
print("="*70)

result = api_get("/markets", {"series_ticker": "KXNFLGAME", "limit": 50})
markets = result.get("markets", [])
print(f"Found {len(markets)} markets in KXNFLGAME series\n")

for m in markets[:20]:  # Just first 20
    ticker = m.get("ticker")
    title = m.get("title")
    status = m.get("status")
    yes_bid = m.get("yes_bid")
    yes_ask = m.get("yes_ask")

    print(f"Ticker: {ticker}")
    print(f"  Title: {title}")
    print(f"  Status: {status}")
    print(f"  Yes Bid/Ask: {yes_bid}/{yes_ask}")
    print()

# Also check MVE single game
print("="*70)
print("MVE NFL SINGLE GAME (KXMVENFLSINGLEGAME)")
print("="*70)

result = api_get("/markets", {"series_ticker": "KXMVENFLSINGLEGAME", "limit": 50})
markets = result.get("markets", [])
print(f"Found {len(markets)} markets in KXMVENFLSINGLEGAME series\n")

for m in markets[:10]:
    ticker = m.get("ticker")
    title = m.get("title")
    status = m.get("status")

    # Filter for non-parlay (no comma in title)
    if "," not in title:
        print(f"Ticker: {ticker}")
        print(f"  Title: {title}")
        print(f"  Status: {status}")
        print()
