"""
Find ALL markets correlated to Ravens-Steelers game:
- Game ML (source of truth)
- Spread markets
- Total points markets
- AFC North winner
- AFC Champion
- Super Bowl winner
- Props (anytime TD, passing yards, etc.)
"""
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

def sign_request(method, path, timestamp_ms):
    message = f"{timestamp_ms}{method}{path}".encode()
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode()

def api_get(endpoint, params=None):
    path = f"/trade-api/v2{endpoint}"
    timestamp_ms = int(time.time() * 1000)
    signature = sign_request("GET", path, timestamp_ms)
    headers = {
        "KALSHI-ACCESS-KEY": api_key_id,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": str(timestamp_ms)
    }
    r = requests.get(f"https://api.elections.kalshi.com{path}", headers=headers, params=params or {}, timeout=30)
    return r.json()

def get_market_info(ticker):
    """Get detailed market info including orderbook"""
    try:
        m = api_get(f"/markets/{ticker}")
        market = m.get("market", {})

        ob = api_get(f"/markets/{ticker}/orderbook", {"depth": 5})
        orderbook = ob.get("orderbook", {})

        return {
            "ticker": ticker,
            "title": market.get("title"),
            "status": market.get("status"),
            "yes_bid": market.get("yes_bid"),
            "yes_ask": market.get("yes_ask"),
            "last_price": market.get("last_price"),
            "volume": market.get("volume"),
            "open_interest": market.get("open_interest"),
            "orderbook_yes": orderbook.get("yes", [])[:3],
            "orderbook_no": orderbook.get("no", [])[:3],
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}

# Series to check
SERIES_TO_CHECK = [
    ("KXNFLGAME", "NFL Game Winner"),
    ("KXNFLSPREAD", "NFL Spread"),
    ("KXNFLTOTAL", "NFL Total Points"),
    ("KXNFLTEAMTOTAL", "NFL Team Total Points"),
    ("KXNFLAFCNORTH", "AFC North Winner"),
    ("KXNFLAFCCHAMP", "AFC Champion"),
    ("KXNFC", "NFC Championship"),
    ("KXAFC", "AFC Championship"),
    ("KXNFLPLAYOFF", "NFL Playoff Qualifiers"),
    ("KXNFLANYTD", "NFL Anytime TD"),
    ("KXNFLFIRSTTD", "NFL First TD"),
    ("KXNFL2TD", "NFL 2+ TDs"),
    ("KXNFLMVP", "NFL MVP"),
]

print("="*80)
print("FINDING ALL RAVENS/STEELERS CORRELATED MARKETS")
print("="*80)

all_related_markets = {}

for series_ticker, series_name in SERIES_TO_CHECK:
    print(f"\nChecking {series_name} ({series_ticker})...")

    try:
        result = api_get("/markets", {"series_ticker": series_ticker, "limit": 200})
        markets = result.get("markets", [])

        # Filter for Ravens/Steelers related
        related = []
        for m in markets:
            title = m.get("title", "").lower()
            ticker = m.get("ticker", "").lower()

            if any(kw in title or kw in ticker for kw in ["bal", "pit", "ravens", "steelers", "baltimore", "pittsburgh"]):
                related.append(m)

        if related:
            print(f"  Found {len(related)} Ravens/Steelers markets")
            all_related_markets[series_name] = related

            for m in related[:5]:  # Show first 5
                print(f"    - {m.get('ticker')}: {m.get('title', '')[:50]}")
                print(f"      Status: {m.get('status')} | Bid/Ask: {m.get('yes_bid')}/{m.get('yes_ask')} | Vol: {m.get('volume')}")
        else:
            print(f"  No Ravens/Steelers markets found")

    except Exception as e:
        print(f"  Error: {e}")

# Now get detailed info for the most important markets
print("\n" + "="*80)
print("DETAILED MARKET ANALYSIS")
print("="*80)

key_tickers = [
    # Game ML (source of truth)
    "KXNFLGAME-26JAN04BALPIT-BAL",
    "KXNFLGAME-26JAN04BALPIT-PIT",
    # AFC North
    "KXNFLAFCNORTH-25-BAL",
    "KXNFLAFCNORTH-25-PIT",
]

# Find spread markets
if "NFL Spread" in all_related_markets:
    for m in all_related_markets["NFL Spread"]:
        key_tickers.append(m.get("ticker"))

# Find total markets
if "NFL Total Points" in all_related_markets:
    for m in all_related_markets["NFL Total Points"]:
        key_tickers.append(m.get("ticker"))

# Find team total markets
if "NFL Team Total Points" in all_related_markets:
    for m in all_related_markets["NFL Team Total Points"]:
        key_tickers.append(m.get("ticker"))

# Find AFC Champion markets
if "AFC Champion" in all_related_markets:
    for m in all_related_markets["AFC Champion"]:
        key_tickers.append(m.get("ticker"))

# Find playoff markets
if "NFL Playoff Qualifiers" in all_related_markets:
    for m in all_related_markets["NFL Playoff Qualifiers"]:
        key_tickers.append(m.get("ticker"))

# Dedupe
key_tickers = list(set(key_tickers))

print(f"\nAnalyzing {len(key_tickers)} key markets in detail...")

detailed_markets = {}
for ticker in key_tickers:
    if ticker:
        info = get_market_info(ticker)
        if "error" not in info:
            detailed_markets[ticker] = info

# Group by type and compare
print("\n" + "="*80)
print("MARKET COMPARISON TABLE")
print("="*80)

# Sort by type
game_ml = []
spreads = []
totals = []
team_totals = []
afc_north = []
afc_champ = []
playoffs = []
other = []

for ticker, info in detailed_markets.items():
    if "KXNFLGAME" in ticker:
        game_ml.append(info)
    elif "SPREAD" in ticker:
        spreads.append(info)
    elif "TEAMTOTAL" in ticker:
        team_totals.append(info)
    elif "TOTAL" in ticker:
        totals.append(info)
    elif "AFCNORTH" in ticker:
        afc_north.append(info)
    elif "AFCCHAMP" in ticker:
        afc_champ.append(info)
    elif "PLAYOFF" in ticker:
        playoffs.append(info)
    else:
        other.append(info)

def print_market_group(name, markets):
    if not markets:
        return
    print(f"\n### {name}")
    print("-"*70)
    for m in markets:
        spread = (m.get('yes_ask', 0) or 0) - (m.get('yes_bid', 0) or 0)
        print(f"  {m.get('ticker', 'N/A')}")
        print(f"    Title: {m.get('title', 'N/A')[:60]}")
        print(f"    Status: {m.get('status')} | Bid/Ask: {m.get('yes_bid')}/{m.get('yes_ask')} | Spread: {spread}¢")
        print(f"    Volume: {m.get('volume'):,} | OI: {m.get('open_interest', 'N/A')}")
        if m.get('orderbook_yes'):
            print(f"    Top Yes bids: {m.get('orderbook_yes')}")

print_market_group("GAME MONEYLINE (Source of Truth)", game_ml)
print_market_group("SPREAD MARKETS", spreads)
print_market_group("TOTAL POINTS", totals)
print_market_group("TEAM TOTALS", team_totals)
print_market_group("AFC NORTH WINNER", afc_north)
print_market_group("AFC CHAMPION", afc_champ)
print_market_group("PLAYOFF QUALIFIERS", playoffs)
print_market_group("OTHER", other)

# Summary stats
print("\n" + "="*80)
print("SUMMARY: SPREAD ANALYSIS")
print("="*80)

all_markets = game_ml + spreads + totals + team_totals + afc_north + afc_champ + playoffs
active_markets = [m for m in all_markets if m.get("status") == "active"]

print(f"\nTotal markets found: {len(all_markets)}")
print(f"Active markets: {len(active_markets)}")

if active_markets:
    avg_spread = sum((m.get('yes_ask', 0) or 0) - (m.get('yes_bid', 0) or 0) for m in active_markets) / len(active_markets)
    print(f"Average bid-ask spread: {avg_spread:.1f}¢")

    print("\nMarkets by spread width (tightest = most efficient):")
    for m in sorted(active_markets, key=lambda x: (x.get('yes_ask', 0) or 0) - (x.get('yes_bid', 0) or 0)):
        spread = (m.get('yes_ask', 0) or 0) - (m.get('yes_bid', 0) or 0)
        print(f"  {spread:2}¢ spread: {m.get('ticker', 'N/A')[:50]}")
