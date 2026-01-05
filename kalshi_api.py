"""
Kalshi API wrapper for the stale order sniper.
Handles authentication and provides clean interfaces for REST + WebSocket.
"""
import json
import time
import base64
import requests
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from datetime import datetime


class KalshiAPI:
    def __init__(self, config_path: str = None):
        """Initialize with config from ~/.kalshi/config.json"""
        if config_path is None:
            config_path = Path.home() / ".kalshi" / "config.json"

        with open(config_path) as f:
            config = json.load(f)

        self.api_key_id = config["api_key_id"]
        self.base_url = config.get("base_url", "https://api.elections.kalshi.com/trade-api/v2")

        # Load private key
        with open(config["private_key_path"], "rb") as f:
            self.private_key = serialization.load_pem_private_key(f.read(), password=None)

    def _sign_request(self, method: str, path: str, timestamp_ms: int) -> str:
        """Sign request using RSA-PSS"""
        message = f"{timestamp_ms}{method}{path}".encode()
        signature = self.private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return base64.b64encode(signature).decode()

    def _get_headers(self, method: str, path: str) -> dict:
        """Get authenticated headers for a request"""
        timestamp_ms = int(time.time() * 1000)
        signature = self._sign_request(method, path, timestamp_ms)

        return {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": str(timestamp_ms),
            "Content-Type": "application/json"
        }

    def _request(self, method: str, endpoint: str, params: dict = None, data: dict = None) -> dict:
        """Make authenticated request to Kalshi API"""
        path = f"/trade-api/v2{endpoint}"
        url = f"{self.base_url.rstrip('/trade-api/v2')}{path}"

        headers = self._get_headers(method, path)

        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=data
        )

        if response.status_code != 200:
            print(f"Error {response.status_code}: {response.text}")
            response.raise_for_status()

        return response.json()

    # ============== PUBLIC MARKET DATA ==============

    def get_markets(self, status: str = "open", series_ticker: str = None,
                    event_ticker: str = None, limit: int = 100, cursor: str = None) -> dict:
        """Get list of markets"""
        params = {"limit": limit, "status": status}
        if series_ticker:
            params["series_ticker"] = series_ticker
        if event_ticker:
            params["event_ticker"] = event_ticker
        if cursor:
            params["cursor"] = cursor

        return self._request("GET", "/markets", params=params)

    def get_market(self, ticker: str) -> dict:
        """Get single market details"""
        return self._request("GET", f"/markets/{ticker}")

    def get_orderbook(self, ticker: str, depth: int = 10) -> dict:
        """Get current orderbook for a market"""
        return self._request("GET", f"/markets/{ticker}/orderbook", params={"depth": depth})

    def get_trades(self, ticker: str = None, limit: int = 100,
                   min_ts: int = None, max_ts: int = None, cursor: str = None) -> dict:
        """Get trade history"""
        params = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        if min_ts:
            params["min_ts"] = min_ts
        if max_ts:
            params["max_ts"] = max_ts
        if cursor:
            params["cursor"] = cursor

        return self._request("GET", "/markets/trades", params=params)

    def get_events(self, status: str = "open", series_ticker: str = None,
                   limit: int = 100, cursor: str = None) -> dict:
        """Get list of events (collections of related markets)"""
        params = {"limit": limit, "status": status}
        if series_ticker:
            params["series_ticker"] = series_ticker
        if cursor:
            params["cursor"] = cursor

        return self._request("GET", "/events", params=params)

    def get_event(self, event_ticker: str) -> dict:
        """Get single event details with all its markets"""
        return self._request("GET", f"/events/{event_ticker}")

    # ============== TRADING ==============

    def get_balance(self) -> dict:
        """Get account balance"""
        return self._request("GET", "/portfolio/balance")

    def get_positions(self) -> dict:
        """Get current positions"""
        return self._request("GET", "/portfolio/positions")

    def create_order(self, ticker: str, side: str, count: int,
                     order_type: str = "market", yes_price: int = None,
                     no_price: int = None, expiration_ts: int = None) -> dict:
        """
        Place an order.
        - side: "yes" or "no"
        - order_type: "market" or "limit"
        - yes_price/no_price: in cents (1-99)
        - count: number of contracts
        """
        data = {
            "ticker": ticker,
            "action": "buy",  # We're always buying to hit stale orders
            "side": side,
            "count": count,
            "type": order_type
        }

        if order_type == "limit":
            if side == "yes" and yes_price:
                data["yes_price"] = yes_price
            elif side == "no" and no_price:
                data["no_price"] = no_price

        if expiration_ts:
            data["expiration_ts"] = expiration_ts

        return self._request("POST", "/portfolio/orders", data=data)

    def cancel_order(self, order_id: str) -> dict:
        """Cancel an existing order"""
        return self._request("DELETE", f"/portfolio/orders/{order_id}")


def search_sports_markets(api: KalshiAPI, search_term: str = None) -> list:
    """Search for sports markets containing a search term"""
    all_markets = []
    cursor = None

    while True:
        result = api.get_markets(status="open", limit=200, cursor=cursor)
        markets = result.get("markets", [])

        for m in markets:
            # Filter for sports-related markets
            title = m.get("title", "").lower()
            ticker = m.get("ticker", "").lower()

            if search_term:
                search_lower = search_term.lower()
                if search_lower in title or search_lower in ticker:
                    all_markets.append(m)
            else:
                # Return all if no search term
                all_markets.append(m)

        cursor = result.get("cursor")
        if not cursor or not markets:
            break

    return all_markets


if __name__ == "__main__":
    # Quick test
    print("Testing Kalshi API connection...")
    api = KalshiAPI()

    # Test balance
    try:
        balance = api.get_balance()
        print(f"✓ Connected! Balance: ${balance.get('balance', 0) / 100:.2f}")
    except Exception as e:
        print(f"✗ Balance check failed: {e}")

    # Search for Ravens/Steelers markets
    print("\nSearching for Ravens markets...")
    ravens_markets = search_sports_markets(api, "ravens")
    print(f"Found {len(ravens_markets)} Ravens markets")

    for m in ravens_markets[:10]:
        print(f"  - {m['ticker']}: {m['title']}")

    print("\nSearching for Steelers markets...")
    steelers_markets = search_sports_markets(api, "steelers")
    print(f"Found {len(steelers_markets)} Steelers markets")

    for m in steelers_markets[:10]:
        print(f"  - {m['ticker']}: {m['title']}")
