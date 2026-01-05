"""Quick one-shot comparison"""
import json
import time
import base64
import requests
from pathlib import Path
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
    r = requests.get(f"https://api.elections.kalshi.com{path}", headers=headers, params=params or {}, timeout=15)
    return r.json()

markets = {
    "BAL Game ML": "KXNFLGAME-26JAN04BALPIT-BAL",
    "BAL AFC North": "KXNFLAFCNORTH-25-BAL",
    "PIT Game ML": "KXNFLGAME-26JAN04BALPIT-PIT",
    "PIT AFC North": "KXNFLAFCNORTH-25-PIT"
}

print("Fetching market data...")
for name, ticker in markets.items():
    try:
        m = api_get(f"/markets/{ticker}")
        market = m.get("market", {})
        print(f"\n{name} ({ticker})")
        print(f"  Status: {market.get('status')}")
        print(f"  Yes Bid/Ask: {market.get('yes_bid')}/{market.get('yes_ask')}")
        print(f"  Last Price: {market.get('last_price')}")
    except Exception as e:
        print(f"\n{name}: ERROR - {e}")

print("\n" + "="*60)
print("ANALYSIS")
print("="*60)
