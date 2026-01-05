"""
Real-time comparison of Ravens-Steelers ML vs AFC North markets.
Shows the gap/edge between equivalent markets.
"""
import json
import time
import base64
import requests
from pathlib import Path
from datetime import datetime
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
    r = requests.get(f"https://api.elections.kalshi.com{path}", headers=headers, params=params or {}, timeout=10)
    return r.json()

def get_market_snapshot(ticker: str) -> dict:
    """Get current market state"""
    try:
        market = api_get(f"/markets/{ticker}")
        ob = api_get(f"/markets/{ticker}/orderbook", {"depth": 3})

        return {
            "ticker": ticker,
            "yes_bid": market.get("market", {}).get("yes_bid", 0),
            "yes_ask": market.get("market", {}).get("yes_ask", 0),
            "no_bid": market.get("market", {}).get("no_bid", 0),
            "no_ask": market.get("market", {}).get("no_ask", 0),
            "last_price": market.get("market", {}).get("last_price", 0),
            "orderbook": ob.get("orderbook", {}),
            "status": market.get("market", {}).get("status", "unknown")
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}

# Market tickers
MARKETS = {
    "bal_ml": "KXNFLGAME-26JAN04BALPIT-BAL",
    "pit_ml": "KXNFLGAME-26JAN04BALPIT-PIT",
    "bal_afc": "KXNFLAFCNORTH-25-BAL",
    "pit_afc": "KXNFLAFCNORTH-25-PIT"
}

def print_comparison():
    """Print side-by-side comparison of markets"""
    snapshots = {}
    for name, ticker in MARKETS.items():
        snapshots[name] = get_market_snapshot(ticker)

    print(f"\n{'='*80}")
    print(f"MARKET COMPARISON - {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*80}")

    # Ravens comparison
    print("\n🏈 BALTIMORE RAVENS")
    print("-"*40)
    bal_ml = snapshots["bal_ml"]
    bal_afc = snapshots["bal_afc"]

    if "error" not in bal_ml and "error" not in bal_afc:
        ml_mid = (bal_ml["yes_bid"] + bal_ml["yes_ask"]) / 2
        afc_mid = (bal_afc["yes_bid"] + bal_afc["yes_ask"]) / 2

        print(f"  Game ML:    Bid {bal_ml['yes_bid']:3}  Ask {bal_ml['yes_ask']:3}  Mid {ml_mid:.1f}")
        print(f"  AFC North:  Bid {bal_afc['yes_bid']:3}  Ask {bal_afc['yes_ask']:3}  Mid {afc_mid:.1f}")

        gap = bal_ml["yes_bid"] - bal_afc["yes_ask"]
        print(f"\n  💰 GAP: ML Bid ({bal_ml['yes_bid']}) - AFC Ask ({bal_afc['yes_ask']}) = {gap} cents")

        if gap > 0:
            print(f"  ✅ EDGE EXISTS: Buy AFC North at {bal_afc['yes_ask']}, should be worth {bal_ml['yes_bid']}")
        elif gap >= -2:
            print(f"  ⚠️  Small gap - monitor for opportunities")
        else:
            print(f"  ❌ No edge - markets in sync")

    # Steelers comparison
    print("\n🏈 PITTSBURGH STEELERS")
    print("-"*40)
    pit_ml = snapshots["pit_ml"]
    pit_afc = snapshots["pit_afc"]

    if "error" not in pit_ml and "error" not in pit_afc:
        ml_mid = (pit_ml["yes_bid"] + pit_ml["yes_ask"]) / 2
        afc_mid = (pit_afc["yes_bid"] + pit_afc["yes_ask"]) / 2

        print(f"  Game ML:    Bid {pit_ml['yes_bid']:3}  Ask {pit_ml['yes_ask']:3}  Mid {ml_mid:.1f}")
        print(f"  AFC North:  Bid {pit_afc['yes_bid']:3}  Ask {pit_afc['yes_ask']:3}  Mid {afc_mid:.1f}")

        gap = pit_ml["yes_bid"] - pit_afc["yes_ask"]
        print(f"\n  💰 GAP: ML Bid ({pit_ml['yes_bid']}) - AFC Ask ({pit_afc['yes_ask']}) = {gap} cents")

        if gap > 0:
            print(f"  ✅ EDGE EXISTS: Buy AFC North at {pit_afc['yes_ask']}, should be worth {pit_ml['yes_bid']}")
        elif gap >= -2:
            print(f"  ⚠️  Small gap - monitor for opportunities")
        else:
            print(f"  ❌ No edge - markets in sync")

    # Orderbook depth
    print("\n📊 ORDERBOOK DEPTH")
    print("-"*40)
    for name, snap in snapshots.items():
        if "error" not in snap and snap.get("orderbook"):
            ob = snap["orderbook"]
            yes_depth = ob.get("yes", [])
            print(f"  {name}: {len(yes_depth)} yes levels")

    return snapshots

if __name__ == "__main__":
    print("Comparing Ravens-Steelers ML vs AFC North markets...")
    print("(Assuming Ravens win = Ravens win AFC North)")

    # Single snapshot
    snapshots = print_comparison()

    # Check if game is still active
    if snapshots["bal_ml"].get("status") == "active":
        print("\n" + "="*80)
        print("GAME IS ACTIVE - Monitoring for opportunities...")
        print("Press Ctrl+C to stop")
        print("="*80)

        try:
            while True:
                time.sleep(5)  # Poll every 5 seconds
                print_comparison()
        except KeyboardInterrupt:
            print("\nStopped monitoring.")
    else:
        print(f"\nGame status: {snapshots['bal_ml'].get('status', 'unknown')}")
        print("Game may be over or not started yet.")
