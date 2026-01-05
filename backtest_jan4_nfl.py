"""
Comprehensive Backtest: All NFL Games on January 4, 2026

This script analyzes ALL markets related to the Ravens-Steelers game
to find stale order opportunities after ML price moves.
"""
import json
import time
import base64
import requests
from pathlib import Path
from datetime import datetime, timedelta
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

def get_trades(ticker, limit=15000):
    """Get trades for a ticker with pagination"""
    all_trades = []
    cursor = None
    pages = 0

    while pages < 20:  # Max 20 pages
        params = {"ticker": ticker, "limit": 1000}
        if cursor:
            params["cursor"] = cursor

        result = api_get("/markets/trades", params)
        trades = result.get("trades", [])
        all_trades.extend(trades)

        cursor = result.get("cursor")
        pages += 1

        if not cursor or not trades:
            break

    return all_trades

def parse_time(trade):
    ts = trade.get("created_time", "")
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except:
        return datetime.now()

def find_ml_moves(trades, min_move=5):
    """Find significant price moves in ML market"""
    if len(trades) < 2:
        return []

    sorted_trades = sorted(trades, key=lambda t: t.get("created_time", ""))
    moves = []
    prev_price = None
    prev_time = None

    for t in sorted_trades:
        price = t.get("yes_price", 0)
        curr_time = parse_time(t)

        if prev_price is not None:
            delta = price - prev_price
            if abs(delta) >= min_move:
                moves.append({
                    "time": curr_time,
                    "prev_time": prev_time,
                    "old_price": prev_price,
                    "new_price": price,
                    "delta": delta
                })
        prev_price = price
        prev_time = curr_time

    return moves

def analyze_staleness(ml_moves, target_trades, window_sec=60):
    """
    For each ML move, check if target market trades happened at stale prices.
    """
    opportunities = []

    if not ml_moves or not target_trades:
        return opportunities

    sorted_target = sorted(target_trades, key=lambda t: t.get("created_time", ""))

    for move in ml_moves:
        move_time = move["time"]
        new_ml = move["new_price"]
        old_ml = move["old_price"]
        delta = move["delta"]

        for t in sorted_target:
            trade_time = parse_time(t)
            lag = (trade_time - move_time).total_seconds()

            # Only trades 0-60 seconds after ML move
            if 0 < lag <= window_sec:
                trade_price = t.get("yes_price", 0)
                trade_count = t.get("count", 0)
                taker_side = t.get("taker_side", "")

                # Check if trade is at stale price
                if delta > 0:  # ML went up
                    if trade_price < new_ml - 3:
                        edge = new_ml - trade_price
                        opportunities.append({
                            "ml_move_time": move_time,
                            "ml_old": old_ml,
                            "ml_new": new_ml,
                            "ml_delta": delta,
                            "trade_time": trade_time,
                            "trade_price": trade_price,
                            "trade_count": trade_count,
                            "lag_sec": lag,
                            "edge": edge,
                            "direction": "buy_yes"
                        })

                elif delta < 0:  # ML went down
                    if trade_price > new_ml + 3:
                        edge = trade_price - new_ml
                        opportunities.append({
                            "ml_move_time": move_time,
                            "ml_old": old_ml,
                            "ml_new": new_ml,
                            "ml_delta": delta,
                            "trade_time": trade_time,
                            "trade_price": trade_price,
                            "trade_count": trade_count,
                            "lag_sec": lag,
                            "edge": edge,
                            "direction": "sell_yes"
                        })

    return opportunities


print("="*80)
print("COMPREHENSIVE BACKTEST: NFL January 4, 2026")
print("="*80)
print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Step 1: Find all markets for the Ravens-Steelers game
print("\n" + "="*80)
print("STEP 1: DISCOVERING ALL MARKETS FOR BAL @ PIT")
print("="*80)

GAME_CODE = "26JAN04BALPIT"
all_markets = {}

# Series to check
SERIES_TO_CHECK = [
    ("KXNFLGAME", "Game ML"),
    ("KXNFLSPREAD", "Spread"),
    ("KXNFLTOTAL", "Total Points"),
    ("KXNFLTEAMTOTAL", "Team Total"),
    ("KXNFLANYTD", "Anytime TD"),
    ("KXNFLFIRSTTD", "First TD"),
    ("KXNFL2TD", "2+ TDs"),
    ("KXNFLAFCNORTH", "AFC North"),
    ("KXNFLAFCCHAMP", "AFC Champion"),
    ("KXNFLNFCCHAMP", "NFC Champion"),
    ("KXNFLPLAYOFF", "Playoff"),
    ("KXMVENFLSINGLEGAME", "MVE Parlay"),
]

for series, name in SERIES_TO_CHECK:
    try:
        result = api_get("/markets", {"series_ticker": series, "limit": 200})
        markets = result.get("markets", [])

        # Filter for BAL/PIT related
        related = []
        for m in markets:
            ticker = m.get("ticker", "")
            title = m.get("title", "").lower()

            # Match game code or team names
            if GAME_CODE in ticker or "bal" in ticker.lower() or "pit" in ticker.lower():
                related.append(m)
            elif "ravens" in title or "steelers" in title or "baltimore" in title or "pittsburgh" in title:
                related.append(m)

        if related:
            all_markets[name] = related
            print(f"  {name}: {len(related)} markets")
    except Exception as e:
        print(f"  {name}: Error - {e}")

total_markets = sum(len(m) for m in all_markets.values())
print(f"\nTotal markets found: {total_markets}")

# Step 2: Get ML trades (source of truth)
print("\n" + "="*80)
print("STEP 2: FETCHING ML TRADES (Source of Truth)")
print("="*80)

ml_ticker_pit = "KXNFLGAME-26JAN04BALPIT-PIT"
ml_ticker_bal = "KXNFLGAME-26JAN04BALPIT-BAL"

print(f"Fetching {ml_ticker_pit}...")
ml_trades_pit = get_trades(ml_ticker_pit)
print(f"  Got {len(ml_trades_pit)} trades")

print(f"Fetching {ml_ticker_bal}...")
ml_trades_bal = get_trades(ml_ticker_bal)
print(f"  Got {len(ml_trades_bal)} trades")

# Find moves in both
ml_moves_pit = find_ml_moves(ml_trades_pit, min_move=5)
ml_moves_bal = find_ml_moves(ml_trades_bal, min_move=5)

print(f"\nPIT ML significant moves (>5 cents): {len(ml_moves_pit)}")
print(f"BAL ML significant moves (>5 cents): {len(ml_moves_bal)}")

# Use the one with more moves
if len(ml_moves_pit) >= len(ml_moves_bal):
    ml_moves = ml_moves_pit
    ml_ticker = ml_ticker_pit
    print(f"\nUsing PIT ML as primary signal ({len(ml_moves)} moves)")
else:
    ml_moves = ml_moves_bal
    ml_ticker = ml_ticker_bal
    print(f"\nUsing BAL ML as primary signal ({len(ml_moves)} moves)")

# Show sample moves
print("\nSample ML moves:")
for m in ml_moves[:10]:
    print(f"  {m['time'].strftime('%H:%M:%S')}: {m['old_price']} -> {m['new_price']} ({m['delta']:+d})")

# Step 3: Analyze each market type
print("\n" + "="*80)
print("STEP 3: ANALYZING STALE ORDERS BY MARKET TYPE")
print("="*80)

results = {}

for market_type, markets in all_markets.items():
    if market_type == "Game ML":
        continue  # Skip ML - that's our source of truth

    print(f"\n### {market_type} ###")
    type_opps = []

    for m in markets:
        ticker = m.get("ticker")
        title = m.get("title", "")[:50]
        vol = m.get("volume", 0)

        if not ticker:
            continue

        try:
            trades = get_trades(ticker, limit=5000)

            if len(trades) < 5:
                continue

            opps = analyze_staleness(ml_moves, trades, window_sec=60)

            if opps:
                type_opps.extend(opps)
                total_edge = sum(o["edge"] for o in opps)
                avg_edge = total_edge / len(opps)
                avg_lag = sum(o["lag_sec"] for o in opps) / len(opps)

                print(f"  {ticker[:45]}")
                print(f"    Trades: {len(trades):,} | Opps: {len(opps)} | Edge: {total_edge}¢ | Avg: {avg_edge:.1f}¢ | Lag: {avg_lag:.1f}s")
        except Exception as e:
            print(f"  {ticker[:45]}: Error - {e}")

    if type_opps:
        results[market_type] = {
            "opportunities": len(type_opps),
            "total_edge": sum(o["edge"] for o in type_opps),
            "avg_edge": sum(o["edge"] for o in type_opps) / len(type_opps),
            "avg_lag": sum(o["lag_sec"] for o in type_opps) / len(type_opps),
            "details": type_opps[:5]  # Save sample
        }

# Step 4: Summary
print("\n" + "="*80)
print("STEP 4: BACKTEST RESULTS SUMMARY")
print("="*80)

print("\n{:<25} {:>10} {:>12} {:>10} {:>10}".format(
    "Market Type", "Opps", "Total Edge", "Avg Edge", "Avg Lag"
))
print("-"*70)

grand_total_opps = 0
grand_total_edge = 0

for market_type, data in sorted(results.items(), key=lambda x: x[1]["total_edge"], reverse=True):
    print("{:<25} {:>10} {:>11}¢ {:>9.1f}¢ {:>9.1f}s".format(
        market_type[:25],
        data["opportunities"],
        data["total_edge"],
        data["avg_edge"],
        data["avg_lag"]
    ))
    grand_total_opps += data["opportunities"]
    grand_total_edge += data["total_edge"]

print("-"*70)
print("{:<25} {:>10} {:>11}¢".format("TOTAL", grand_total_opps, grand_total_edge))

# Convert to dollars
profit_dollars = grand_total_edge / 100
print(f"\n💰 THEORETICAL PROFIT: ${profit_dollars:.2f}")

# Lag time distribution
print("\n" + "="*80)
print("STEP 5: OPPORTUNITY TIMING ANALYSIS")
print("="*80)

all_opps = []
for data in results.values():
    all_opps.extend(data.get("details", []))

if all_opps:
    buckets = defaultdict(list)
    for o in all_opps:
        if o["lag_sec"] < 5:
            buckets["0-5s"].append(o)
        elif o["lag_sec"] < 15:
            buckets["5-15s"].append(o)
        elif o["lag_sec"] < 30:
            buckets["15-30s"].append(o)
        else:
            buckets["30-60s"].append(o)

    print("\nOpportunities by lag time (when you could have hit the stale order):")
    for bucket in ["0-5s", "5-15s", "15-30s", "30-60s"]:
        opps = buckets.get(bucket, [])
        if opps:
            avg_edge = sum(o["edge"] for o in opps) / len(opps)
            print(f"  {bucket}: {len(opps)} opps, avg {avg_edge:.1f}¢ edge")

# Key insights
print("\n" + "="*80)
print("KEY INSIGHTS: Ravens @ Steelers (Jan 4, 2026)")
print("="*80)

print(f"""
📊 GAME STATS:
- ML moves detected: {len(ml_moves)}
- Total stale opportunities: {grand_total_opps}
- Theoretical profit: ${profit_dollars:.2f}

🎯 BEST MARKET TYPES:""")

for market_type, data in sorted(results.items(), key=lambda x: x[1]["total_edge"], reverse=True)[:3]:
    print(f"  1. {market_type}: {data['opportunities']} opps, {data['total_edge']}¢ edge")

print(f"""
⏱️ TIMING:
- Average lag: {sum(d['avg_lag'] for d in results.values()) / len(results) if results else 0:.1f}s
- Window is tradeable manually or via bot

💡 ACTIONABLE TAKEAWAYS:
- Focus on highest-edge market types
- Set up alerts for ML moves >5 cents
- Execute within 30 seconds of ML move
- Expected profit per primetime game: ${profit_dollars:.2f}
""")

# Save detailed results
output = {
    "game": "BAL @ PIT",
    "date": "2026-01-04",
    "ml_moves": len(ml_moves),
    "total_opportunities": grand_total_opps,
    "total_edge_cents": grand_total_edge,
    "profit_dollars": profit_dollars,
    "by_market_type": {k: {"opportunities": v["opportunities"], "total_edge": v["total_edge"], "avg_edge": v["avg_edge"], "avg_lag": v["avg_lag"]} for k, v in results.items()}
}

with open("backtest_jan4_results.json", "w") as f:
    json.dump(output, f, indent=2, default=str)

print(f"\nDetailed results saved to backtest_jan4_results.json")
