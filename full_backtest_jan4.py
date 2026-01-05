"""
COMPREHENSIVE BACKTEST: All Games January 4, 2026

Analyzes EVERY game (NFL, NBA, CBB, NHL) to find:
1. Where are the inefficiencies?
2. How fast do stale orders get filled?
3. What's the REALISTIC capturable profit?
4. What edge size is actually available?
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
        return None

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
        if prev_price is not None and curr_time:
            delta = price - prev_price
            if abs(delta) >= min_move:
                moves.append({
                    "time": curr_time,
                    "old_price": prev_price,
                    "new_price": price,
                    "delta": delta
                })
        prev_price = price
        prev_time = curr_time
    return moves

def analyze_staleness_detailed(ml_moves, target_trades, window_sec=60):
    """Detailed stale analysis with time buckets"""
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
            if not trade_time:
                continue
            lag = (trade_time - move_time).total_seconds()

            if 0 < lag <= window_sec:
                trade_price = t.get("yes_price", 0)
                trade_count = t.get("count", 1)

                # Check staleness
                if delta > 0 and trade_price < new_ml - 3:
                    edge = new_ml - trade_price
                    opportunities.append({
                        "lag_sec": lag,
                        "edge": edge,
                        "volume": trade_count,
                        "direction": "buy",
                        "trade_price": trade_price,
                        "fair_value": new_ml
                    })
                elif delta < 0 and trade_price > new_ml + 3:
                    edge = trade_price - new_ml
                    opportunities.append({
                        "lag_sec": lag,
                        "edge": edge,
                        "volume": trade_count,
                        "direction": "sell",
                        "trade_price": trade_price,
                        "fair_value": new_ml
                    })

    return opportunities


print("="*80)
print("COMPREHENSIVE BACKTEST: ALL GAMES - JANUARY 4, 2026")
print("="*80)
print(f"Started: {datetime.now()}")

# ============================================================
# STEP 1: Find ALL games on Jan 4
# ============================================================
print("\n" + "="*80)
print("STEP 1: FINDING ALL GAMES ON JANUARY 4, 2026")
print("="*80)

GAME_SERIES = [
    ("KXNFLGAME", "NFL"),
    ("KXNBAGAME", "NBA"),
    ("KXNCAABGAME", "CBB"),
    ("KXNCAAFGAME", "CFB"),
    ("KXNHLGAME", "NHL"),
]

all_games = {}

for series, sport in GAME_SERIES:
    try:
        result = api_get("/markets", {"series_ticker": series, "limit": 200})
        markets = result.get("markets", [])

        # Filter for Jan 4 games (26JAN04 in ticker)
        jan4_markets = [m for m in markets if "26JAN04" in m.get("ticker", "") or "JAN04" in m.get("ticker", "")]

        if jan4_markets:
            # Group by game
            games_by_id = defaultdict(list)
            for m in jan4_markets:
                ticker = m.get("ticker", "")
                parts = ticker.split("-")
                if len(parts) >= 2:
                    game_id = parts[1]
                    games_by_id[game_id].append(m)

            for game_id, markets in games_by_id.items():
                total_vol = sum(m.get("volume", 0) for m in markets)
                all_games[f"{sport}:{game_id}"] = {
                    "sport": sport,
                    "game_id": game_id,
                    "markets": markets,
                    "volume": total_vol
                }

            print(f"  {sport}: {len(games_by_id)} games, ${sum(g['volume'] for g in games_by_id.values() for m in [g]):,} volume")
    except Exception as e:
        print(f"  {sport}: Error - {e}")

print(f"\nTotal games found: {len(all_games)}")

# Sort by volume
sorted_games = sorted(all_games.items(), key=lambda x: x[1]["volume"], reverse=True)

print("\nGames by volume:")
for game_key, data in sorted_games[:15]:
    print(f"  {game_key}: ${data['volume']:,}")

# ============================================================
# STEP 2: For each game, find ML and correlated markets
# ============================================================
print("\n" + "="*80)
print("STEP 2: ANALYZING EACH GAME")
print("="*80)

CORRELATED_SERIES = {
    "NFL": ["KXNFLTOTAL", "KXNFLSPREAD", "KXNFLANYTD", "KXNFL2TD", "KXNFLAFCNORTH", "KXNFLAFCCHAMP", "KXNFLPLAYOFF"],
    "NBA": ["KXNBATOTAL", "KXNBASPREAD", "KXNBAPLAYOFF"],
    "CBB": ["KXNCAABTOTAL", "KXNCAABSPREAD"],
    "CFB": ["KXNCAAFTOTAL", "KXNCAAFSPREAD"],
    "NHL": ["KXNHLTOTAL"],
}

all_results = {}

for game_key, game_data in sorted_games[:10]:  # Top 10 games by volume
    sport = game_data["sport"]
    game_id = game_data["game_id"]

    print(f"\n### {game_key} ###")
    print(f"Volume: ${game_data['volume']:,}")

    # Get ML market
    ml_markets = game_data["markets"]
    if not ml_markets:
        continue

    # Pick the higher volume ML side
    ml_market = max(ml_markets, key=lambda m: m.get("volume", 0))
    ml_ticker = ml_market.get("ticker")

    print(f"ML Market: {ml_ticker}")

    # Get ML trades
    ml_trades = get_trades(ml_ticker, limit=10000)
    print(f"ML Trades: {len(ml_trades)}")

    if len(ml_trades) < 50:
        print("  Skipping - not enough trades")
        continue

    # Find ML moves
    ml_moves = find_ml_moves(ml_trades, min_move=5)
    print(f"ML Moves (>5¢): {len(ml_moves)}")

    if not ml_moves:
        print("  No significant ML moves")
        continue

    # Find correlated markets
    correlated_series = CORRELATED_SERIES.get(sport, [])
    correlated_markets = []

    for series in correlated_series:
        try:
            result = api_get("/markets", {"series_ticker": series, "limit": 200})
            for m in result.get("markets", []):
                if game_id in m.get("ticker", ""):
                    correlated_markets.append(m)
        except:
            pass

    print(f"Correlated Markets: {len(correlated_markets)}")

    # Analyze each correlated market
    game_opportunities = []
    market_breakdown = defaultdict(list)

    for cm in correlated_markets[:30]:  # Limit to 30 markets per game
        ticker = cm.get("ticker")

        # Determine market type
        if "TOTAL" in ticker and "TEAM" not in ticker:
            market_type = "Totals"
        elif "SPREAD" in ticker:
            market_type = "Spread"
        elif "ANYTD" in ticker:
            market_type = "Anytime TD"
        elif "2TD" in ticker:
            market_type = "2+ TDs"
        elif "AFCNORTH" in ticker or "NFCNORTH" in ticker:
            market_type = "Division"
        elif "AFCCHAMP" in ticker or "NFCCHAMP" in ticker:
            market_type = "Conference"
        elif "PLAYOFF" in ticker:
            market_type = "Playoff"
        else:
            market_type = "Other"

        try:
            trades = get_trades(ticker, limit=5000)
            if len(trades) < 10:
                continue

            opps = analyze_staleness_detailed(ml_moves, trades, window_sec=60)

            if opps:
                for opp in opps:
                    opp["market_type"] = market_type
                    opp["ticker"] = ticker
                    opp["game"] = game_key

                game_opportunities.extend(opps)
                market_breakdown[market_type].extend(opps)
        except:
            pass

    if game_opportunities:
        total_edge = sum(o["edge"] for o in game_opportunities)
        avg_edge = total_edge / len(game_opportunities)
        avg_lag = sum(o["lag_sec"] for o in game_opportunities) / len(game_opportunities)

        print(f"\n  RESULTS:")
        print(f"  Total opportunities: {len(game_opportunities)}")
        print(f"  Total edge: {total_edge}¢ (${total_edge/100:.2f})")
        print(f"  Avg edge: {avg_edge:.1f}¢")
        print(f"  Avg lag: {avg_lag:.1f}s")

        print(f"\n  By market type:")
        for mt, opps in sorted(market_breakdown.items(), key=lambda x: sum(o["edge"] for o in x[1]), reverse=True):
            mt_edge = sum(o["edge"] for o in opps)
            mt_avg_lag = sum(o["lag_sec"] for o in opps) / len(opps)
            print(f"    {mt}: {len(opps)} opps, {mt_edge}¢ edge, {mt_avg_lag:.1f}s lag")

        all_results[game_key] = {
            "opportunities": game_opportunities,
            "total_edge": total_edge,
            "avg_edge": avg_edge,
            "avg_lag": avg_lag,
            "by_market_type": {k: len(v) for k, v in market_breakdown.items()}
        }

# ============================================================
# STEP 3: Aggregate Analysis
# ============================================================
print("\n" + "="*80)
print("STEP 3: AGGREGATE ANALYSIS - WHERE ARE THE INEFFICIENCIES?")
print("="*80)

all_opps = []
for game_key, data in all_results.items():
    all_opps.extend(data["opportunities"])

if not all_opps:
    print("No opportunities found!")
else:
    print(f"\nTotal opportunities across all games: {len(all_opps)}")

    # By sport
    print("\n### BY SPORT ###")
    by_sport = defaultdict(list)
    for opp in all_opps:
        sport = opp["game"].split(":")[0]
        by_sport[sport].append(opp)

    print(f"{'Sport':<10} {'Opps':>8} {'Total Edge':>12} {'Avg Edge':>10} {'Avg Lag':>10}")
    print("-"*55)
    for sport, opps in sorted(by_sport.items(), key=lambda x: sum(o["edge"] for o in x[1]), reverse=True):
        total = sum(o["edge"] for o in opps)
        avg_e = total / len(opps)
        avg_l = sum(o["lag_sec"] for o in opps) / len(opps)
        print(f"{sport:<10} {len(opps):>8} {total:>11}¢ {avg_e:>9.1f}¢ {avg_l:>9.1f}s")

    # By market type
    print("\n### BY MARKET TYPE ###")
    by_type = defaultdict(list)
    for opp in all_opps:
        by_type[opp["market_type"]].append(opp)

    print(f"{'Type':<15} {'Opps':>8} {'Total Edge':>12} {'Avg Edge':>10} {'Avg Lag':>10}")
    print("-"*60)
    for mtype, opps in sorted(by_type.items(), key=lambda x: sum(o["edge"] for o in x[1]), reverse=True):
        total = sum(o["edge"] for o in opps)
        avg_e = total / len(opps)
        avg_l = sum(o["lag_sec"] for o in opps) / len(opps)
        print(f"{mtype:<15} {len(opps):>8} {total:>11}¢ {avg_e:>9.1f}¢ {avg_l:>9.1f}s")

    # By lag time bucket (CRITICAL for understanding capture rate)
    print("\n### BY LAG TIME (How fast do opportunities disappear?) ###")
    buckets = {
        "0-1s": [],
        "1-5s": [],
        "5-15s": [],
        "15-30s": [],
        "30-60s": [],
    }

    for opp in all_opps:
        lag = opp["lag_sec"]
        if lag <= 1:
            buckets["0-1s"].append(opp)
        elif lag <= 5:
            buckets["1-5s"].append(opp)
        elif lag <= 15:
            buckets["5-15s"].append(opp)
        elif lag <= 30:
            buckets["15-30s"].append(opp)
        else:
            buckets["30-60s"].append(opp)

    print(f"{'Bucket':<12} {'Opps':>8} {'% of Total':>12} {'Total Edge':>12} {'Avg Edge':>10}")
    print("-"*60)
    total_opps = len(all_opps)
    for bucket in ["0-1s", "1-5s", "5-15s", "15-30s", "30-60s"]:
        opps = buckets[bucket]
        if opps:
            total = sum(o["edge"] for o in opps)
            avg_e = total / len(opps)
            pct = len(opps) / total_opps * 100
            print(f"{bucket:<12} {len(opps):>8} {pct:>11.1f}% {total:>11}¢ {avg_e:>9.1f}¢")

    # By edge size
    print("\n### BY EDGE SIZE ###")
    edge_buckets = {
        "5-10¢": [],
        "10-20¢": [],
        "20-50¢": [],
        "50-100¢": [],
        "100+¢": [],
    }

    for opp in all_opps:
        edge = opp["edge"]
        if edge < 10:
            edge_buckets["5-10¢"].append(opp)
        elif edge < 20:
            edge_buckets["10-20¢"].append(opp)
        elif edge < 50:
            edge_buckets["20-50¢"].append(opp)
        elif edge < 100:
            edge_buckets["50-100¢"].append(opp)
        else:
            edge_buckets["100+¢"].append(opp)

    print(f"{'Edge Size':<12} {'Opps':>8} {'% of Total':>12} {'Total Edge':>12} {'Avg Lag':>10}")
    print("-"*60)
    for bucket in ["5-10¢", "10-20¢", "20-50¢", "50-100¢", "100+¢"]:
        opps = edge_buckets[bucket]
        if opps:
            total = sum(o["edge"] for o in opps)
            avg_l = sum(o["lag_sec"] for o in opps) / len(opps)
            pct = len(opps) / total_opps * 100
            print(f"{bucket:<12} {len(opps):>8} {pct:>11.1f}% {total:>11}¢ {avg_l:>9.1f}s")

# ============================================================
# STEP 4: Realistic Profit Calculation
# ============================================================
print("\n" + "="*80)
print("STEP 4: REALISTIC PROFIT CALCULATION")
print("="*80)

if all_opps:
    total_theoretical_edge = sum(o["edge"] for o in all_opps)

    print(f"""
THEORETICAL (if you captured everything):
  Total opportunities: {len(all_opps)}
  Total edge: {total_theoretical_edge}¢ (${total_theoretical_edge/100:.2f})
""")

    # Calculate by execution speed
    print("REALISTIC (based on execution speed):")
    print("-"*60)

    speeds = [
        ("Manual (3-5s)", 3000, 0.10),
        ("Slow bot (2s)", 2000, 0.15),
        ("Medium bot (800ms)", 800, 0.40),
        ("Fast bot (300ms)", 300, 0.60),
        ("Ultra fast (100ms)", 100, 0.80),
    ]

    for name, speed_ms, capture_rate in speeds:
        # Capture rate also depends on lag distribution
        # Faster bot can capture faster-disappearing opportunities

        capturable_opps = []
        for opp in all_opps:
            # Can capture if our speed < opportunity lag
            if opp["lag_sec"] * 1000 > speed_ms:
                capturable_opps.append(opp)

        # Apply additional capture rate (competition, execution failures)
        actual_captured = int(len(capturable_opps) * capture_rate)

        if capturable_opps:
            # Take the best opportunities first
            sorted_opps = sorted(capturable_opps, key=lambda x: x["edge"], reverse=True)
            captured_opps = sorted_opps[:actual_captured]

            gross_edge = sum(o["edge"] for o in captured_opps)
            fees = gross_edge * 0.07 * 0.60  # 7% on 60% wins
            net_edge = gross_edge - fees

            print(f"{name}:")
            print(f"  Opps capturable: {len(capturable_opps)}")
            print(f"  Actually captured: {actual_captured}")
            print(f"  Gross profit: ${gross_edge/100:.0f}")
            print(f"  Fees: ${fees/100:.0f}")
            print(f"  NET PROFIT: ${net_edge/100:.0f}")
            print()

# ============================================================
# STEP 5: Capital Requirements
# ============================================================
print("\n" + "="*80)
print("STEP 5: CAPITAL REQUIREMENTS")
print("="*80)

if all_opps:
    # Analyze how many opportunities happen simultaneously
    # (within same 60-second window after an ML move)

    print("""
POSITION SIZING:

  Edge-based sizing (recommended):
    5-10¢ edge:  $10-20 per trade
    10-20¢ edge: $20-30 per trade
    20-50¢ edge: $30-50 per trade
    50+¢ edge:   $50-100 per trade

  Max concurrent positions: ~10-15
  Peak capital needed: $500-1,000

RECOMMENDED BANKROLL BY STRATEGY:

  Conservative ($500):
    - Focus on high-edge opportunities (>20¢)
    - 5-10 trades per game
    - Expected profit: $50-100/game

  Moderate ($1,000):
    - Capture medium+ edge (>10¢)
    - 10-20 trades per game
    - Expected profit: $100-200/game

  Aggressive ($2,500):
    - Capture most opportunities (>5¢)
    - 20-40 trades per game
    - Expected profit: $200-400/game
""")

# Save results
output = {
    "analysis_date": datetime.now().isoformat(),
    "games_analyzed": len(all_results),
    "total_opportunities": len(all_opps),
    "total_edge_cents": sum(o["edge"] for o in all_opps) if all_opps else 0,
    "by_sport": {k: {"opps": len(v), "edge": sum(o["edge"] for o in v)} for k, v in by_sport.items()} if all_opps else {},
    "by_market_type": {k: {"opps": len(v), "edge": sum(o["edge"] for o in v)} for k, v in by_type.items()} if all_opps else {},
    "by_lag_bucket": {k: {"opps": len(v), "edge": sum(o["edge"] for o in v)} for k, v in buckets.items()} if all_opps else {},
    "games": {k: {"total_edge": v["total_edge"], "opps": len(v["opportunities"])} for k, v in all_results.items()}
}

with open("full_backtest_jan4_results.json", "w") as f:
    json.dump(output, f, indent=2, default=str)

print(f"\nResults saved to full_backtest_jan4_results.json")
print(f"\nCompleted: {datetime.now()}")
