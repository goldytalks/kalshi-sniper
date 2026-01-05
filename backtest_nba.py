"""
Backtest NBA markets for stale order opportunities.
Same methodology as NFL - find ML moves and check correlated markets.
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

def get_trades(ticker, limit=10000):
    all_trades = []
    cursor = None
    pages = 0
    while pages < 15:
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
                moves.append({"time": curr_time, "old_price": prev_price, "new_price": price, "delta": delta})
        prev_price = price
        prev_time = curr_time
    return moves

def analyze_staleness(ml_moves, target_trades, window_sec=60):
    opportunities = []
    if not ml_moves or not target_trades:
        return opportunities
    sorted_target = sorted(target_trades, key=lambda t: t.get("created_time", ""))
    for move in ml_moves:
        move_time = move["time"]
        new_ml = move["new_price"]
        delta = move["delta"]
        for t in sorted_target:
            trade_time = parse_time(t)
            lag = (trade_time - move_time).total_seconds()
            if 0 < lag <= window_sec:
                trade_price = t.get("yes_price", 0)
                if delta > 0 and trade_price < new_ml - 3:
                    edge = new_ml - trade_price
                    opportunities.append({"ml_new": new_ml, "trade_price": trade_price, "lag_sec": lag, "edge": edge})
                elif delta < 0 and trade_price > new_ml + 3:
                    edge = trade_price - new_ml
                    opportunities.append({"ml_new": new_ml, "trade_price": trade_price, "lag_sec": lag, "edge": edge})
    return opportunities

print("="*80)
print("NBA STALE ORDER BACKTEST")
print("="*80)

# First, find NBA game markets
print("\n1. FINDING NBA GAME MARKETS")
print("-"*60)

# Check MVE NBA single game series (these have the game winners)
result = api_get("/markets", {"series_ticker": "KXMVENBASINGLEGAME", "limit": 200})
mve_markets = result.get("markets", [])

# Also check standard NBA game series
result2 = api_get("/markets", {"series_ticker": "KXNBAGAME", "limit": 200})
nba_markets = result2.get("markets", [])

all_nba_markets = mve_markets + nba_markets
print(f"Found {len(all_nba_markets)} NBA-related markets")

# Find recent games with trades
nba_games = {}
for m in all_nba_markets:
    ticker = m.get("ticker", "")
    title = m.get("title", "")
    vol = m.get("volume", 0)
    status = m.get("status", "")

    # Extract game identifier from ticker
    # Look for markets that could be game winners
    if vol > 10000:  # Has some volume
        # Try to identify the game
        # MVE tickers look like: KXMVENBASINGLEGAME-S2025XXXXX-YYYYY
        parts = ticker.split("-")
        if len(parts) >= 2:
            game_id = parts[1] if len(parts) > 1 else ticker

            if game_id not in nba_games:
                nba_games[game_id] = {"markets": [], "game_id": game_id}

            nba_games[game_id]["markets"].append({
                "ticker": ticker,
                "title": title,
                "volume": vol,
                "status": status,
                "bid": m.get("yes_bid", 0),
                "ask": m.get("yes_ask", 0)
            })

print(f"Identified {len(nba_games)} potential NBA games")

# Show top games by volume
top_games = sorted(nba_games.items(), key=lambda x: sum(m["volume"] for m in x[1]["markets"]), reverse=True)

print("\nTop NBA games by volume:")
for game_id, data in top_games[:10]:
    total_vol = sum(m["volume"] for m in data["markets"])
    print(f"  {game_id}: {len(data['markets'])} markets, ${total_vol:,} volume")
    for m in data["markets"][:2]:
        print(f"    {m['ticker'][:50]}: {m['title'][:40]}")

# Now let's look for NBA totals markets
print("\n2. FINDING NBA TOTALS MARKETS")
print("-"*60)

result = api_get("/markets", {"series_ticker": "KXNBATOTAL", "limit": 200})
nba_totals = result.get("markets", [])
print(f"Found {len(nba_totals)} NBA total markets")

# Show some with volume
active_totals = [m for m in nba_totals if m.get("volume", 0) > 10000]
print(f"Active totals (>$10k vol): {len(active_totals)}")

for m in sorted(active_totals, key=lambda x: x.get("volume", 0), reverse=True)[:10]:
    print(f"  {m.get('ticker')[:50]}")
    print(f"    Vol: ${m.get('volume', 0):,} | Bid/Ask: {m.get('yes_bid')}/{m.get('yes_ask')}")

# Find a game with both ML and Totals to backtest
print("\n3. BACKTEST: FINDING GAME WITH ML + TOTALS")
print("-"*60)

# Look for tickers with similar game identifiers
# NBA totals tickers look like: KXNBATOTAL-26JAN04OKCLAL-220
# Let's find games with both ML and totals

# Get recent trades for a high-volume NBA total
if active_totals:
    # Pick one with good volume
    test_total = sorted(active_totals, key=lambda x: x.get("volume", 0), reverse=True)[0]
    test_ticker = test_total.get("ticker")
    print(f"\nAnalyzing: {test_ticker}")
    print(f"Title: {test_total.get('title')}")

    trades = get_trades(test_ticker, limit=5000)
    print(f"Trades: {len(trades)}")

    if trades:
        moves = find_ml_moves(trades, min_move=5)
        print(f"Significant moves (>5 cents): {len(moves)}")

        for m in moves[:5]:
            print(f"  {m['time'].strftime('%H:%M:%S')}: {m['old_price']} -> {m['new_price']} ({m['delta']:+d})")

# Try to find corresponding game ML
# Extract game code from total ticker
if active_totals:
    total_ticker = active_totals[0].get("ticker", "")
    # KXNBATOTAL-26JAN04OKCLAL-220 -> 26JAN04OKCLAL
    parts = total_ticker.split("-")
    if len(parts) >= 2:
        game_code = parts[1]
        print(f"\nLooking for game ML with code: {game_code}")

        # Search for matching game winner market
        # Try MVE series
        all_markets = []
        for series in ["KXMVENBASINGLEGAME", "KXNBAGAME"]:
            result = api_get("/markets", {"series_ticker": series, "limit": 200})
            all_markets.extend(result.get("markets", []))

        matching = [m for m in all_markets if game_code in m.get("ticker", "")]
        print(f"Found {len(matching)} matching game markets")

        for m in matching[:5]:
            print(f"  {m.get('ticker')}: Vol ${m.get('volume', 0):,}")

print("\n4. COMPREHENSIVE NBA ANALYSIS")
print("-"*60)

# Analyze whatever NBA markets we can find with good data
results = {}

# Check NBA championship market (like AFC Champion for NFL)
print("\nChecking NBA Championship market...")
result = api_get("/markets", {"series_ticker": "KXNBACHAMP", "limit": 50})
nba_champ = result.get("markets", [])
print(f"Found {len(nba_champ)} NBA championship markets")

for m in nba_champ[:5]:
    ticker = m.get("ticker")
    vol = m.get("volume", 0)
    if vol > 100000:
        print(f"  {ticker}: Vol ${vol:,}")
        trades = get_trades(ticker, limit=3000)
        if trades:
            print(f"    Trades: {len(trades)}")

# Analyze any MVE NBA markets with high volume
print("\nAnalyzing high-volume MVE NBA markets...")

for m in sorted(mve_markets, key=lambda x: x.get("volume", 0), reverse=True)[:5]:
    ticker = m.get("ticker")
    title = m.get("title", "")
    vol = m.get("volume", 0)

    if vol < 50000:
        continue

    print(f"\n{ticker[:50]}")
    print(f"  Title: {title[:60]}")
    print(f"  Volume: ${vol:,}")

    trades = get_trades(ticker, limit=5000)
    print(f"  Trades: {len(trades)}")

    if len(trades) > 100:
        moves = find_ml_moves(trades, min_move=5)
        print(f"  Significant moves: {len(moves)}")

        # Look for stale patterns within the same market
        # (Price reverting after spike)
        opps = analyze_staleness(moves, trades, window_sec=30)
        if opps:
            total_edge = sum(o["edge"] for o in opps)
            avg_edge = total_edge / len(opps)
            avg_lag = sum(o["lag_sec"] for o in opps) / len(opps)
            print(f"  Stale opportunities: {len(opps)}")
            print(f"  Total edge: {total_edge}¢ | Avg: {avg_edge:.1f}¢ | Lag: {avg_lag:.1f}s")

            results[ticker] = {
                "title": title,
                "trades": len(trades),
                "moves": len(moves),
                "opportunities": len(opps),
                "total_edge": total_edge,
                "avg_edge": avg_edge
            }

print("\n" + "="*80)
print("5. NBA BACKTEST SUMMARY")
print("="*80)

if results:
    print("\n{:<40} {:>8} {:>6} {:>10}".format("Market", "Opps", "Avg Edge", "Total Edge"))
    print("-"*70)
    for ticker, data in sorted(results.items(), key=lambda x: x[1]["total_edge"], reverse=True):
        print("{:<40} {:>8} {:>6.1f}¢ {:>10}¢".format(
            ticker[:40], data["opportunities"], data["avg_edge"], data["total_edge"]
        ))
else:
    print("\nNo stale opportunities detected in sampled NBA markets.")
    print("This could mean:")
    print("  1. NBA markets are more efficient")
    print("  2. Need to analyze during live games")
    print("  3. Totals correlation works differently in basketball")

print("""
NBA KEY INSIGHTS:
- NBA has multiple games per night (more opportunities)
- Basketball has more scoring = more ML moves per game
- Totals markets should correlate with game flow
- Need to test during LIVE games for best results
""")
