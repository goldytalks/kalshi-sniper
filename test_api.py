"""Quick API test - just test connection and find Ravens/Steelers markets"""
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
base_url = "https://api.elections.kalshi.com/trade-api/v2"

# Load private key
with open(config["private_key_path"], "rb") as f:
    private_key = serialization.load_pem_private_key(f.read(), password=None)

def sign_request(method: str, path: str, timestamp_ms: int) -> str:
    message = f"{timestamp_ms}{method}{path}".encode()
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
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
        "Content-Type": "application/json"
    }

# Test 1: Get balance
print("Test 1: Getting balance...")
path = "/trade-api/v2/portfolio/balance"
headers = get_headers("GET", path)
try:
    r = requests.get(f"https://api.elections.kalshi.com{path}", headers=headers, timeout=10)
    print(f"  Status: {r.status_code}")
    if r.status_code == 200:
        balance = r.json()
        print(f"  Balance: ${balance.get('balance', 0) / 100:.2f}")
    else:
        print(f"  Error: {r.text}")
except Exception as e:
    print(f"  Exception: {e}")

# Test 2: Get a few markets
print("\nTest 2: Getting markets...")
path = "/trade-api/v2/markets"
headers = get_headers("GET", path)
try:
    r = requests.get(
        f"https://api.elections.kalshi.com{path}",
        headers=headers,
        params={"limit": 10, "status": "open"},
        timeout=10
    )
    print(f"  Status: {r.status_code}")
    if r.status_code == 200:
        markets = r.json().get("markets", [])
        print(f"  Found {len(markets)} markets")
        for m in markets[:5]:
            print(f"    - {m.get('ticker')}: {m.get('title', '')[:60]}")
    else:
        print(f"  Error: {r.text}")
except Exception as e:
    print(f"  Exception: {e}")

# Test 3: Search for NFL specifically
print("\nTest 3: Searching for NFL markets...")
path = "/trade-api/v2/events"
headers = get_headers("GET", path)
try:
    r = requests.get(
        f"https://api.elections.kalshi.com{path}",
        headers=headers,
        params={"limit": 50, "status": "open"},
        timeout=15
    )
    print(f"  Status: {r.status_code}")
    if r.status_code == 200:
        events = r.json().get("events", [])
        print(f"  Found {len(events)} events")
        for e in events:
            title = e.get("title", "").lower()
            if "nfl" in title or "ravens" in title or "steelers" in title or "afc" in title:
                print(f"    - {e.get('event_ticker')}: {e.get('title')}")
    else:
        print(f"  Error: {r.text}")
except Exception as e:
    print(f"  Exception: {e}")
