"""
Backtest: Analyze historical trades to find stale order opportunities.

Strategy: When Game ML moves significantly, check if AFC North (or other correlated
markets) had stale prices that could be exploited.
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

def get_all_trades(ticker: str, min_ts: int = None, max_ts: int = None) -> list:
    """Get all trades for a ticker within time range"""
    all_trades = []
    cursor = None

    while True:
        params = {"ticker": ticker, "limit": 1000}
        if min_ts:
            params["min_ts"] = min_ts
        if max_ts:
            params["max_ts"] = max_ts
        if cursor:
            params["cursor"] = cursor

        result = api_get("/markets/trades", params)
        trades = result.get("trades", [])
        all_trades.extend(trades)

        cursor = result.get("cursor")
        if not cursor or not trades:
            break

        print(f"  Fetched {len(all_trades)} trades for {ticker}...")

    return all_trades

def parse_trade_time(trade: dict) -> datetime:
    """Parse trade timestamp to datetime"""
    ts_str = trade.get("created_time", "")
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except:
        return datetime.now()

def analyze_price_moves(trades: list, min_move: int = 3) -> list:
    """Find significant price moves in trade history"""
    if not trades:
        return []

    moves = []
    sorted_trades = sorted(trades, key=lambda t: t.get("created_time", ""))

    prev_price = None
    for trade in sorted_trades:
        price = trade.get("yes_price", 0)
        if prev_price is not None:
            delta = price - prev_price
            if abs(delta) >= min_move:
                moves.append({
                    "time": parse_trade_time(trade),
                    "old_price": prev_price,
                    "new_price": price,
                    "delta": delta,
                    "trade": trade
                })
        prev_price = price

    return moves

def find_stale_trades(ml_moves: list, correlated_trades: list, window_seconds: int = 30) -> list:
    """
    For each ML move, find trades on correlated market that happened at stale prices.
    A "stale" trade is one where the price doesn't reflect the ML move.
    """
    stale_opportunities = []

    correlated_by_time = sorted(correlated_trades, key=lambda t: t.get("created_time", ""))

    for move in ml_moves:
        move_time = move["time"]
        new_ml_price = move["new_price"]
        old_ml_price = move["old_price"]

        # Look at correlated trades in the window after ML moved
        for trade in correlated_by_time:
            trade_time = parse_trade_time(trade)
            time_diff = (trade_time - move_time).total_seconds()

            # Only look at trades 0-30 seconds AFTER the ML move
            if 0 < time_diff <= window_seconds:
                trade_price = trade.get("yes_price", 0)

                # "Stale" = traded at old ML price when it should be at new ML price
                # If ML went UP and correlated trade is still LOW, that's stale
                if move["delta"] > 0:  # ML went up
                    expected_min = new_ml_price - 3  # Allow 3 cent tolerance
                    if trade_price < expected_min:
                        edge = new_ml_price - trade_price
                        stale_opportunities.append({
                            "ml_move_time": move_time,
                            "ml_old": old_ml_price,
                            "ml_new": new_ml_price,
                            "trade_time": trade_time,
                            "trade_price": trade_price,
                            "lag_seconds": time_diff,
                            "edge_cents": edge,
                            "direction": "buy_yes"
                        })

                elif move["delta"] < 0:  # ML went down
                    expected_max = new_ml_price + 3  # Allow 3 cent tolerance
                    if trade_price > expected_max:
                        edge = trade_price - new_ml_price
                        stale_opportunities.append({
                            "ml_move_time": move_time,
                            "ml_old": old_ml_price,
                            "ml_new": new_ml_price,
                            "trade_time": trade_time,
                            "trade_price": trade_price,
                            "lag_seconds": time_diff,
                            "edge_cents": edge,
                            "direction": "buy_no"
                        })

    return stale_opportunities


def run_backtest():
    """Run backtest on recent games"""
    print("="*70)
    print("KALSHI STALE ORDER BACKTEST")
    print("="*70)

    # Look at recent NFL games - get trades from last 7 days
    now = datetime.now()
    week_ago = now - timedelta(days=7)
    min_ts = int(week_ago.timestamp())

    # Find recent NFL game markets
    print("\nFinding recent NFL game markets...")
    result = api_get("/markets", {"series_ticker": "KXNFLGAME", "limit": 100})
    game_markets = result.get("markets", [])

    # Filter for games that have trades (active or recently finalized)
    analyzed_games = []

    for market in game_markets:
        ticker = market.get("ticker")
        title = market.get("title")
        status = market.get("status")

        if not ticker or "Winner" not in title:
            continue

        # Extract team from ticker (e.g., KXNFLGAME-26JAN04BALPIT-BAL -> BAL)
        parts = ticker.split("-")
        if len(parts) < 3:
            continue

        team = parts[-1]
        game_code = parts[-2] if len(parts) > 2 else ""

        print(f"\nAnalyzing: {title} ({ticker})")
        print(f"  Status: {status}")

        # Get trades for this market
        trades = get_all_trades(ticker, min_ts=min_ts)
        print(f"  Found {len(trades)} trades")

        if len(trades) < 10:
            print("  Skipping - not enough trades")
            continue

        # Find significant price moves (>3 cents)
        moves = analyze_price_moves(trades, min_move=3)
        print(f"  Found {len(moves)} significant price moves (>3 cents)")

        for move in moves[:5]:  # Show first 5
            print(f"    {move['time'].strftime('%H:%M:%S')}: {move['old_price']} -> {move['new_price']} ({move['delta']:+d})")

        analyzed_games.append({
            "ticker": ticker,
            "title": title,
            "trades": trades,
            "moves": moves
        })

    print("\n" + "="*70)
    print("CROSS-MARKET ANALYSIS")
    print("="*70)

    # Now compare Game ML to AFC North for ravens/steelers
    # This is the key test - do AFC North trades lag behind Game ML moves?

    # Get AFC North trades
    print("\nFetching AFC North market trades...")
    afc_tickers = ["KXNFLAFCNORTH-25-BAL", "KXNFLAFCNORTH-25-PIT"]

    for afc_ticker in afc_tickers:
        print(f"\nAnalyzing {afc_ticker}...")
        afc_trades = get_all_trades(afc_ticker, min_ts=min_ts)
        print(f"  Found {len(afc_trades)} trades")

        if not afc_trades:
            continue

        # Find the corresponding game ML market
        team = afc_ticker.split("-")[-1]  # BAL or PIT
        game_ticker = f"KXNFLGAME-26JAN04BALPIT-{team}"

        print(f"  Comparing to Game ML: {game_ticker}")

        # Get game ML trades and moves
        game_trades = get_all_trades(game_ticker, min_ts=min_ts)
        print(f"  Found {len(game_trades)} game ML trades")

        if not game_trades:
            continue

        ml_moves = analyze_price_moves(game_trades, min_move=5)
        print(f"  Found {len(ml_moves)} significant ML moves (>5 cents)")

        # Find stale opportunities
        stale = find_stale_trades(ml_moves, afc_trades, window_seconds=60)

        print(f"\n  STALE TRADE OPPORTUNITIES FOUND: {len(stale)}")

        if stale:
            total_edge = sum(s["edge_cents"] for s in stale)
            avg_edge = total_edge / len(stale)
            avg_lag = sum(s["lag_seconds"] for s in stale) / len(stale)

            print(f"  Total theoretical edge: {total_edge} cents")
            print(f"  Average edge per trade: {avg_edge:.1f} cents")
            print(f"  Average lag time: {avg_lag:.1f} seconds")

            print("\n  Sample stale trades:")
            for s in stale[:5]:
                print(f"    ML moved {s['ml_old']}->{s['ml_new']} at {s['ml_move_time'].strftime('%H:%M:%S')}")
                print(f"      Trade at {s['trade_price']} happened {s['lag_seconds']:.1f}s later")
                print(f"      Edge: {s['edge_cents']} cents ({s['direction']})")
        else:
            print("  No stale trades detected - markets may be efficient")

    print("\n" + "="*70)
    print("BACKTEST COMPLETE")
    print("="*70)


if __name__ == "__main__":
    run_backtest()
