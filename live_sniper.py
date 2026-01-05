"""
LIVE SNIPER: Real-time alert system for stale order opportunities.

Monitors Game ML markets and alerts when price moves significantly,
then checks correlated markets for stale orders.

Usage: python live_sniper.py [--execute] [--sport NFL|NBA|ALL]
"""
import json
import time
import base64
import requests
import argparse
from pathlib import Path
from datetime import datetime
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
    signature = private_key.sign(message, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
    return base64.b64encode(signature).decode()

def api_get(endpoint, params=None):
    path = f"/trade-api/v2{endpoint}"
    timestamp_ms = int(time.time() * 1000)
    signature = sign_request("GET", path, timestamp_ms)
    headers = {"KALSHI-ACCESS-KEY": api_key_id, "KALSHI-ACCESS-SIGNATURE": signature, "KALSHI-ACCESS-TIMESTAMP": str(timestamp_ms)}
    r = requests.get(f"https://api.elections.kalshi.com{path}", headers=headers, params=params or {}, timeout=10)
    return r.json()

def api_post(endpoint, data):
    path = f"/trade-api/v2{endpoint}"
    timestamp_ms = int(time.time() * 1000)
    signature = sign_request("POST", path, timestamp_ms)
    headers = {"KALSHI-ACCESS-KEY": api_key_id, "KALSHI-ACCESS-SIGNATURE": signature, "KALSHI-ACCESS-TIMESTAMP": str(timestamp_ms), "Content-Type": "application/json"}
    r = requests.post(f"https://api.elections.kalshi.com{path}", headers=headers, json=data, timeout=10)
    return r.json()

class LiveSniper:
    def __init__(self, sport="ALL", execute=False, max_position=50, min_edge=5):
        self.sport = sport
        self.execute = execute
        self.max_position = max_position  # Max $ per trade
        self.min_edge = min_edge  # Minimum edge in cents to trade
        self.price_cache = {}  # Track last known prices
        self.opportunities = []
        self.trades_executed = []

    def get_live_games(self):
        """Find currently active games"""
        live_games = []

        series_to_check = []
        if self.sport in ["NFL", "ALL"]:
            series_to_check.extend([
                ("KXNFLGAME", "NFL"),
                ("KXMVENFLSINGLEGAME", "NFL MVE"),
            ])
        if self.sport in ["NBA", "ALL"]:
            series_to_check.extend([
                ("KXNBAGAME", "NBA"),
                ("KXMVENBASINGLEGAME", "NBA MVE"),
            ])
        if self.sport in ["CBB", "ALL"]:
            series_to_check.extend([
                ("KXNCAABGAME", "CBB"),
            ])

        for series, sport_name in series_to_check:
            try:
                result = api_get("/markets", {"series_ticker": series, "status": "active", "limit": 100})
                markets = result.get("markets", [])

                for m in markets:
                    vol = m.get("volume", 0)
                    bid = m.get("yes_bid", 0)
                    ask = m.get("yes_ask", 0)
                    spread = (ask or 0) - (bid or 0)

                    # High volume + tight spread = likely live game
                    if vol > 50000 and spread <= 5:
                        live_games.append({
                            "ticker": m.get("ticker"),
                            "title": m.get("title"),
                            "sport": sport_name,
                            "bid": bid,
                            "ask": ask,
                            "mid": (bid + ask) / 2 if bid and ask else 0,
                            "volume": vol
                        })
            except:
                pass

        return live_games

    def get_correlated_markets(self, game_ticker):
        """Find markets correlated to a game ML"""
        correlated = []

        # Extract game identifier from ticker
        # e.g., KXNFLGAME-26JAN04BALPIT-BAL -> 26JAN04BALPIT
        parts = game_ticker.split("-")
        if len(parts) < 2:
            return correlated

        game_code = parts[1]

        # Series to check for correlated markets
        corr_series = [
            "KXNFLTOTAL", "KXNBATOTAL",  # Totals
            "KXNFLTEAMTOTAL", "KXNBATEAMTOTAL",  # Team totals
            "KXNFLANYTD",  # Props
            "KXNFLAFCNORTH", "KXNFLNFCNORTH",  # Division
            "KXNFLAFCCHAMP", "KXNFLNFCCHAMP",  # Conference
            "KXNFLPLAYOFF", "KXNBAPLAYOFF",  # Playoffs
        ]

        for series in corr_series:
            try:
                result = api_get("/markets", {"series_ticker": series, "status": "active", "limit": 100})
                markets = result.get("markets", [])

                for m in markets:
                    ticker = m.get("ticker", "")
                    # Match by game code or team abbreviation
                    if game_code in ticker or any(team in ticker for team in game_code[-6:].split()):
                        correlated.append({
                            "ticker": ticker,
                            "title": m.get("title"),
                            "type": series,
                            "bid": m.get("yes_bid", 0),
                            "ask": m.get("yes_ask", 0),
                            "volume": m.get("volume", 0)
                        })
            except:
                pass

        return correlated

    def check_for_move(self, game):
        """Check if game ML has moved significantly"""
        ticker = game["ticker"]
        current_mid = game["mid"]

        if ticker in self.price_cache:
            old_mid = self.price_cache[ticker]
            delta = current_mid - old_mid

            if abs(delta) >= 5:  # 5+ cent move
                self.price_cache[ticker] = current_mid
                return {
                    "ticker": ticker,
                    "old_price": old_mid,
                    "new_price": current_mid,
                    "delta": delta,
                    "direction": "UP" if delta > 0 else "DOWN"
                }

        self.price_cache[ticker] = current_mid
        return None

    def find_stale_orders(self, move, correlated_markets):
        """Find stale orders on correlated markets after ML move"""
        stale = []

        new_ml = move["new_price"]
        direction = move["direction"]

        for market in correlated_markets:
            bid = market.get("bid", 0)
            ask = market.get("ask", 0)

            if not bid or not ask:
                continue

            # If ML went UP, correlated should go UP
            # Stale ASK below new fair value = BUY opportunity
            if direction == "UP":
                if ask < new_ml - self.min_edge:
                    edge = new_ml - ask
                    stale.append({
                        "ticker": market["ticker"],
                        "title": market["title"],
                        "action": "BUY",
                        "price": ask,
                        "fair_value": new_ml,
                        "edge": edge
                    })

            # If ML went DOWN, correlated should go DOWN
            # Stale BID above new fair value = SELL opportunity
            elif direction == "DOWN":
                if bid > new_ml + self.min_edge:
                    edge = bid - new_ml
                    stale.append({
                        "ticker": market["ticker"],
                        "title": market["title"],
                        "action": "SELL",
                        "price": bid,
                        "fair_value": new_ml,
                        "edge": edge
                    })

        return stale

    def execute_trade(self, opportunity):
        """Execute a trade (if enabled)"""
        if not self.execute:
            return {"status": "SIMULATED", "opportunity": opportunity}

        ticker = opportunity["ticker"]
        action = opportunity["action"]
        price = opportunity["price"]

        # Calculate position size (max $50 per trade)
        count = min(self.max_position, 50)

        try:
            if action == "BUY":
                order = api_post("/portfolio/orders", {
                    "ticker": ticker,
                    "action": "buy",
                    "side": "yes",
                    "count": count,
                    "type": "market"
                })
            else:  # SELL (buy NO)
                order = api_post("/portfolio/orders", {
                    "ticker": ticker,
                    "action": "buy",
                    "side": "no",
                    "count": count,
                    "type": "market"
                })

            self.trades_executed.append({
                "time": datetime.now().isoformat(),
                "ticker": ticker,
                "action": action,
                "count": count,
                "price": price,
                "edge": opportunity["edge"],
                "order": order
            })

            return {"status": "EXECUTED", "order": order}
        except Exception as e:
            return {"status": "FAILED", "error": str(e)}

    def print_alert(self, move, stale_orders):
        """Print alert to console"""
        print("\n" + "!"*80)
        print(f"🚨 ALERT: ML MOVED {move['delta']:+.0f}¢ @ {datetime.now().strftime('%H:%M:%S')}")
        print("!"*80)
        print(f"Game: {move['ticker']}")
        print(f"Move: {move['old_price']:.0f} -> {move['new_price']:.0f} ({move['direction']})")

        if stale_orders:
            print(f"\n🎯 FOUND {len(stale_orders)} STALE ORDER OPPORTUNITIES:")
            for so in sorted(stale_orders, key=lambda x: x["edge"], reverse=True):
                print(f"  {so['action']} {so['ticker'][:40]}")
                print(f"    Price: {so['price']}¢ | Fair Value: {so['fair_value']:.0f}¢ | Edge: {so['edge']:.0f}¢")
        else:
            print("\n❌ No stale orders found on correlated markets")

        print("!"*80 + "\n")

    def run(self, poll_interval=2):
        """Main loop - poll markets and alert on opportunities"""
        print("="*80)
        print(f"LIVE SNIPER ACTIVE - Monitoring {self.sport} games")
        print(f"Execute mode: {'ON' if self.execute else 'OFF (simulation)'}")
        print(f"Min edge: {self.min_edge}¢ | Max position: ${self.max_position}")
        print("="*80)
        print("\nPress Ctrl+C to stop\n")

        try:
            while True:
                # Find live games
                live_games = self.get_live_games()

                if not live_games:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] No live games found, waiting...")
                    time.sleep(10)
                    continue

                print(f"[{datetime.now().strftime('%H:%M:%S')}] Monitoring {len(live_games)} live games...")

                for game in live_games:
                    # Check for price move
                    move = self.check_for_move(game)

                    if move:
                        # Found a move! Get correlated markets
                        correlated = self.get_correlated_markets(game["ticker"])

                        # Find stale orders
                        stale = self.find_stale_orders(move, correlated)

                        # Alert
                        self.print_alert(move, stale)

                        # Execute if enabled
                        if stale and self.execute:
                            best_opp = max(stale, key=lambda x: x["edge"])
                            result = self.execute_trade(best_opp)
                            print(f"Trade result: {result}")

                        self.opportunities.append({
                            "time": datetime.now().isoformat(),
                            "move": move,
                            "stale_orders": stale
                        })

                time.sleep(poll_interval)

        except KeyboardInterrupt:
            print("\n\nSniper stopped.")
            self.print_summary()

    def print_summary(self):
        """Print session summary"""
        print("\n" + "="*80)
        print("SESSION SUMMARY")
        print("="*80)
        print(f"Total opportunities detected: {len(self.opportunities)}")
        print(f"Trades executed: {len(self.trades_executed)}")

        if self.trades_executed:
            total_edge = sum(t["edge"] for t in self.trades_executed)
            print(f"Total theoretical edge: {total_edge}¢")

        # Save log
        log = {
            "session_end": datetime.now().isoformat(),
            "opportunities": self.opportunities,
            "trades": self.trades_executed
        }
        with open(f"sniper_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", "w") as f:
            json.dump(log, f, indent=2, default=str)
        print(f"Log saved to sniper_log_*.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live stale order sniper")
    parser.add_argument("--execute", action="store_true", help="Actually execute trades (default: simulation)")
    parser.add_argument("--sport", default="ALL", choices=["NFL", "NBA", "CBB", "ALL"], help="Sport to monitor")
    parser.add_argument("--min-edge", type=int, default=5, help="Minimum edge in cents")
    parser.add_argument("--max-position", type=int, default=50, help="Max position size in dollars")
    parser.add_argument("--interval", type=float, default=2, help="Poll interval in seconds")

    args = parser.parse_args()

    sniper = LiveSniper(
        sport=args.sport,
        execute=args.execute,
        min_edge=args.min_edge,
        max_position=args.max_position
    )
    sniper.run(poll_interval=args.interval)
