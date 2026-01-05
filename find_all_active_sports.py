"""
Find ALL active sports markets across NFL, NBA, CBB, and other January sports.
Categorize by sport and market type.
"""
import json
import time
import base64
import requests
from pathlib import Path
from collections import defaultdict
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

config_path = Path.home() / ".kalshi" / "config.json"
with open(config_path) as f:
    config = json.load(f)

api_key_id = config["api_key_id"]
with open(config["private_key_path"], "rb") as f:
    private_key = serialization.load_pem_private_key(f.read(), password=None)

def sign_request(method, path, timestamp_ms):
    message = f"{timestamp_ms}{method}{path}".encode()
    signature = private_key.sign(message, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
    return base64.b64encode(signature).decode()

def api_get(endpoint, params=None):
    path = f"/trade-api/v2{endpoint}"
    timestamp_ms = int(time.time() * 1000)
    signature = sign_request("GET", path, timestamp_ms)
    headers = {"KALSHI-ACCESS-KEY": api_key_id, "KALSHI-ACCESS-SIGNATURE": signature, "KALSHI-ACCESS-TIMESTAMP": str(timestamp_ms)}
    r = requests.get(f"https://api.elections.kalshi.com{path}", headers=headers, params=params or {}, timeout=30)
    return r.json()

# Sports series to check
SPORTS_SERIES = [
    # NFL
    ("KXNFLGAME", "NFL Game Winner"),
    ("KXNFLSPREAD", "NFL Spread"),
    ("KXNFLTOTAL", "NFL Total Points"),
    ("KXNFLTEAMTOTAL", "NFL Team Totals"),
    ("KXNFLANYTD", "NFL Anytime TD"),
    ("KXNFLFIRSTTD", "NFL First TD"),
    ("KXNFL2TD", "NFL 2+ TDs"),
    ("KXNFLAFCNORTH", "NFL AFC North"),
    ("KXNFLAFCCHAMP", "NFL AFC Champion"),
    ("KXNFLNFCCHAMP", "NFL NFC Champion"),
    ("KXNFLPLAYOFF", "NFL Playoff Qualifiers"),

    # NBA
    ("KXNBAGAME", "NBA Game Winner"),
    ("KXNBASPREAD", "NBA Spread"),
    ("KXNBATOTAL", "NBA Total Points"),
    ("KXNBATEAMTOTAL", "NBA Team Totals"),
    ("KXNBAPLAYOFF", "NBA Playoff"),
    ("KXNBACHAMP", "NBA Champion"),
    ("KXNBAMVP", "NBA MVP"),

    # College Basketball
    ("KXNCAABGAME", "College Basketball Game"),
    ("KXNCAABSPREAD", "College Basketball Spread"),
    ("KXNCAABTOTAL", "College Basketball Total"),
    ("KXMARCHM", "March Madness"),

    # College Football (bowl games)
    ("KXNCAAFGAME", "College Football Game"),
    ("KXNCAAFSPREAD", "College Football Spread"),
    ("KXNCAAFTOTAL", "College Football Total"),

    # NHL
    ("KXNHLGAME", "NHL Game Winner"),
    ("KXNHLTOTAL", "NHL Total"),

    # Soccer
    ("KXSOCCERGAME", "Soccer Game"),

    # MVE (Multi-variant - parlays)
    ("KXMVENFLSINGLEGAME", "MVE NFL Single"),
    ("KXMVENBASINGLEGAME", "MVE NBA Single"),
    ("KXMVESPORTSMULTIGAME", "MVE Sports Multi"),
]

print("="*80)
print("FINDING ALL ACTIVE SPORTS MARKETS")
print("="*80)

all_active = defaultdict(list)
total_markets = 0

for series_ticker, series_name in SPORTS_SERIES:
    try:
        result = api_get("/markets", {"series_ticker": series_ticker, "status": "open", "limit": 200})
        markets = result.get("markets", [])

        # Also check for 'active' status
        result2 = api_get("/markets", {"series_ticker": series_ticker, "status": "active", "limit": 200})
        markets.extend(result2.get("markets", []))

        # Dedupe
        seen = set()
        unique_markets = []
        for m in markets:
            ticker = m.get("ticker")
            if ticker and ticker not in seen:
                seen.add(ticker)
                unique_markets.append(m)

        if unique_markets:
            all_active[series_name] = unique_markets
            total_markets += len(unique_markets)
            print(f"  {series_name}: {len(unique_markets)} active markets")
    except Exception as e:
        pass  # Series might not exist

print(f"\n{'='*80}")
print(f"TOTAL: {total_markets} active sports markets")
print("="*80)

# Detailed breakdown by sport
sports_breakdown = {
    "NFL": [],
    "NBA": [],
    "College Basketball": [],
    "College Football": [],
    "NHL": [],
    "Other": []
}

for series_name, markets in all_active.items():
    if "NFL" in series_name or "nfl" in series_name.lower():
        sports_breakdown["NFL"].extend(markets)
    elif "NBA" in series_name or "nba" in series_name.lower():
        sports_breakdown["NBA"].extend(markets)
    elif "College Basketball" in series_name or "NCAAB" in series_name or "March" in series_name:
        sports_breakdown["College Basketball"].extend(markets)
    elif "College Football" in series_name or "NCAAF" in series_name:
        sports_breakdown["College Football"].extend(markets)
    elif "NHL" in series_name:
        sports_breakdown["NHL"].extend(markets)
    else:
        sports_breakdown["Other"].extend(markets)

print("\n" + "="*80)
print("BREAKDOWN BY SPORT")
print("="*80)

for sport, markets in sports_breakdown.items():
    if markets:
        print(f"\n### {sport}: {len(markets)} markets")

        # Group by market type
        by_type = defaultdict(list)
        for m in markets:
            ticker = m.get("ticker", "")
            if "GAME" in ticker:
                by_type["Game Winner"].append(m)
            elif "SPREAD" in ticker:
                by_type["Spread"].append(m)
            elif "TOTAL" in ticker and "TEAM" not in ticker:
                by_type["Total Points"].append(m)
            elif "TEAMTOTAL" in ticker:
                by_type["Team Total"].append(m)
            elif "ANYTD" in ticker or "TD" in ticker:
                by_type["Touchdowns"].append(m)
            elif "CHAMP" in ticker:
                by_type["Championship"].append(m)
            elif "MVE" in ticker:
                by_type["Parlays (MVE)"].append(m)
            else:
                by_type["Other"].append(m)

        for mtype, mlist in by_type.items():
            print(f"  {mtype}: {len(mlist)}")
            # Show sample with volume
            sorted_by_vol = sorted(mlist, key=lambda x: x.get("volume", 0), reverse=True)
            for m in sorted_by_vol[:3]:
                vol = m.get("volume", 0)
                bid = m.get("yes_bid", 0)
                ask = m.get("yes_ask", 0)
                spread = (ask or 0) - (bid or 0)
                print(f"    {m.get('ticker', '')[:40]}: Vol ${vol:,} | Spread {spread}¢")

# Find LIVE games (games happening now or today)
print("\n" + "="*80)
print("LIVE/TODAY'S GAMES (Highest Priority)")
print("="*80)

# Look for games with high recent volume and tight spreads
live_candidates = []

for sport, markets in sports_breakdown.items():
    for m in markets:
        ticker = m.get("ticker", "")
        vol = m.get("volume", 0)
        bid = m.get("yes_bid", 0)
        ask = m.get("yes_ask", 0)
        spread = (ask or 0) - (bid or 0)

        # High volume + tight spread = likely live
        if vol > 100000 and spread <= 5 and "GAME" in ticker:
            live_candidates.append({
                "sport": sport,
                "ticker": ticker,
                "title": m.get("title", "")[:50],
                "volume": vol,
                "bid": bid,
                "ask": ask,
                "spread": spread
            })

live_candidates.sort(key=lambda x: x["volume"], reverse=True)

print("\nLikely live games (high volume + tight spread):")
for lc in live_candidates[:20]:
    print(f"  {lc['sport']}: {lc['ticker']}")
    print(f"    {lc['title']}")
    print(f"    Vol: ${lc['volume']:,} | Bid/Ask: {lc['bid']}/{lc['ask']} | Spread: {lc['spread']}¢")

# Save summary to JSON
summary = {
    "total_markets": total_markets,
    "by_sport": {sport: len(markets) for sport, markets in sports_breakdown.items()},
    "live_candidates": live_candidates[:20]
}

with open("active_sports_summary.json", "w") as f:
    json.dump(summary, f, indent=2)

print(f"\nSaved summary to active_sports_summary.json")
