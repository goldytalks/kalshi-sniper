# Speed Optimization Plan: Cut Execution Time by 50%+

**Current Performance:** ~2,200ms end-to-end
**Target Performance:** ~1,000ms end-to-end (55% reduction)
**Aggressive Target:** <500ms (77% reduction)

---

## Executive Summary

After deep research into Kalshi's API, public trading repos, and low-latency Python techniques, here are the key findings:

| Optimization | Expected Impact | Effort |
|--------------|-----------------|--------|
| **Persistent aiohttp Session** | -40% latency | Low |
| **uvloop Event Loop** | -25% latency | Low |
| **WebSocket Orderbook Streaming** | -60% latency | Medium |
| **VPS Colocation (NYC)** | -50ms+ network | Medium |
| **Connection Pooling Tuning** | -20% latency | Low |
| **FIX Protocol** | 5-10ms total | High |

---

## Current Bottlenecks Identified

### 1. Creating New ClientSession Per Request (CRITICAL)
```python
# CURRENT (BAD) - in fast_sniper.py:162
async with aiohttp.ClientSession() as session:  # New session every time!
    tasks = []
    for ticker in tickers[:20]:
        tasks.append(api_get_async(session, ...))
```

**Problem:** Each `ClientSession()` creates new TCP connections, performs DNS lookups, and TLS handshakes. This adds **170-220ms overhead per batch**.

**Fix:** Create ONE persistent session at startup, reuse for all requests.

### 2. REST Polling Instead of WebSocket (CRITICAL)
```python
# CURRENT (SLOW) - Polling every 500ms
while True:
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*tasks)
    await asyncio.sleep(poll_interval)  # 500ms delay!
```

**Problem:**
- 500ms minimum delay between price updates
- Each poll = new HTTP request overhead
- Miss fast-moving opportunities

**Fix:** WebSocket subscription gives real-time updates with ~10ms latency.

### 3. Default asyncio Event Loop
**Problem:** Python's default event loop is slow.
**Fix:** uvloop is 2-4x faster, drop-in replacement.

### 4. No Connection Pooling Configuration
**Problem:** Default aiohttp limits may bottleneck parallel requests.
**Fix:** Configure TCPConnector with proper limits.

---

## Optimization Strategy (Prioritized)

### Phase 1: Quick Wins (Low Effort, High Impact)

#### 1.1 Persistent Session with Connection Pool
```python
# Create ONCE at startup
connector = aiohttp.TCPConnector(
    limit=100,           # Total connection pool
    limit_per_host=50,   # Per-host limit
    keepalive_timeout=30,
    enable_cleanup_closed=True,
    force_close=False,   # Reuse connections
)
self.session = aiohttp.ClientSession(
    connector=connector,
    timeout=aiohttp.ClientTimeout(total=5)
)

# Reuse everywhere - don't create new sessions!
async def fetch_orderbooks_parallel(self, tickers):
    tasks = [self.api_get_async(f"/markets/{t}/orderbook") for t in tickers]
    return await asyncio.gather(*tasks)
```

**Expected improvement:** 40% latency reduction
**Source:** [MarketCalls - 70% latency reduction with connection pooling](https://www.marketcalls.in/python/slashing-api-order-latency-upto-70-with-http-connection-pooling.html)

#### 1.2 Install uvloop
```python
# At the very top of fast_sniper.py
import uvloop
uvloop.install()  # Or use uvloop.run(main())
```

**Expected improvement:** 2-4x faster async operations
**Source:** [uvloop GitHub - MagicStack](https://github.com/MagicStack/uvloop)

#### 1.3 Pre-compute Signatures
```python
# Cache recent signatures (they're timestamp-based, but can batch)
# Pre-sign for the next few seconds if needed
```

### Phase 2: WebSocket Implementation (Medium Effort, Highest Impact)

#### 2.1 WebSocket for ML Price Streaming
Kalshi's WebSocket provides real-time ticker updates without polling.

```python
import websockets

WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"

async def connect_websocket(self):
    headers = self._get_ws_auth_headers()

    async with websockets.connect(WS_URL, extra_headers=headers) as ws:
        # Subscribe to ML markets
        await ws.send(json.dumps({
            "id": 1,
            "cmd": "subscribe",
            "params": {
                "channels": ["ticker"],
                "market_tickers": list(self.ml_markets.keys())
            }
        }))

        async for message in ws:
            data = json.loads(message)
            if data.get("type") == "ticker":
                await self.handle_price_update(data)
```

**Expected improvement:** Near-instant price detection (vs 500ms polling)
**Source:** [Kalshi WebSocket Docs](https://docs.kalshi.com/getting_started/quick_start_websockets)

#### 2.2 WebSocket for Orderbook Deltas
```python
# Subscribe to orderbook updates for correlated markets
await ws.send(json.dumps({
    "id": 2,
    "cmd": "subscribe",
    "params": {
        "channels": ["orderbook_delta"],
        "market_tickers": correlated_tickers
    }
}))
```

**Key insight:** Orderbook deltas are incremental - maintain local orderbook state, only receive changes. Much faster than full orderbook REST fetches.

### Phase 3: Infrastructure (Medium Effort)

#### 3.1 VPS Near Kalshi Servers
Kalshi is headquartered in NYC and likely uses AWS us-east-1.

**Recommended:** [QuantVPS Kalshi VPS](https://www.quantvps.com/kalshi-vps)
- NYC-based, <0.52ms to major liquidity providers
- Optimized for prediction market trading
- ~$20-50/month

**Alternative:** AWS EC2 in us-east-1 (Virginia/NYC)
- t3.medium or c5.large for compute
- Use spot instances for cost savings

**Expected improvement:** 50-100ms network latency reduction

### Phase 4: Advanced Optimizations (High Effort)

#### 4.1 FIX Protocol (Institutional)
Kalshi offers FIX 4.4 for lowest latency order execution.
- Contact: [email protected]
- Expected latency: 5-10ms for order execution
- Requires existing FIX infrastructure

**Source:** [Kalshi FIX API](https://docs.kalshi.com/fix)

#### 4.2 Rust OMS Layer
For absolute minimum latency, consider a Rust middle layer:
- [kalshi-oms](https://github.com/milesChild/kalshi-oms) - Rust-based OMS
- [Polymarket-Kalshi-Arbitrage-bot](https://github.com/terauss/Polymarket-Kalshi-Arbitrage-bot) - SIMD-accelerated

#### 4.3 Lock-Free Data Structures
For high-frequency orderbook updates:
```python
# Use atomic operations for orderbook cache
from atomics import atomic  # Or similar
```

---

## Reference Implementations

### High-Performance Kalshi Bots (GitHub)

1. **[terauss/Polymarket-Kalshi-Arbitrage-bot](https://github.com/terauss/Polymarket-Kalshi-Arbitrage-bot)**
   - SIMD-accelerated arbitrage detection
   - Sub-millisecond latency claims
   - Lock-free atomic orderbook cache
   - Rust implementation

2. **[milesChild/kalshi-oms](https://github.com/milesChild/kalshi-oms)**
   - Low-latency Rust OMS
   - TCP connections for client interface
   - RabbitMQ message queue layer

3. **[humz2k/kalshi-python-unofficial](https://github.com/humz2k/kalshi-python-unofficial)**
   - Lightweight Python wrapper
   - WebSocket client implementation
   - Good reference for Python WebSocket code

### Official Kalshi SDK
```bash
pip install kalshi-python
```
- Auto-generated from OpenAPI spec
- Full API coverage
- [Documentation](https://docs.kalshi.com/python-sdk)

---

## Implementation Checklist

### Immediate (This Week)
- [ ] Refactor to persistent aiohttp.ClientSession
- [ ] Add uvloop (`pip install uvloop`)
- [ ] Configure TCPConnector with proper pool limits
- [ ] Benchmark before/after

### Short-Term (Next 2 Weeks)
- [ ] Implement WebSocket connection for ticker streaming
- [ ] Implement WebSocket orderbook delta subscriptions
- [ ] Maintain local orderbook state from deltas
- [ ] Add reconnection logic for WebSocket

### Medium-Term
- [ ] Deploy to NYC VPS (QuantVPS or AWS us-east-1)
- [ ] Benchmark latency from VPS
- [ ] Consider official kalshi-python SDK

### Long-Term (If Needed)
- [ ] Contact Kalshi about FIX access
- [ ] Evaluate Rust implementation for critical path
- [ ] Explore SIMD optimizations

---

## Expected Results

| Phase | Current | After | Improvement |
|-------|---------|-------|-------------|
| Phase 1 (Quick Wins) | 2,200ms | 1,200ms | 45% |
| Phase 2 (WebSocket) | 1,200ms | 400ms | 67% |
| Phase 3 (VPS) | 400ms | 300ms | 25% |
| **Combined** | **2,200ms** | **300ms** | **86%** |

---

## Key Resources

### Documentation
- [Kalshi WebSocket Quick Start](https://docs.kalshi.com/getting_started/quick_start_websockets)
- [Kalshi Orderbook Updates](https://docs.kalshi.com/websockets/orderbook-updates)
- [Kalshi Python SDK](https://docs.kalshi.com/python-sdk)
- [Kalshi FIX API](https://docs.kalshi.com/fix)

### Libraries
- [aiohttp Documentation](https://docs.aiohttp.org/en/stable/http_request_lifecycle.html)
- [uvloop GitHub](https://github.com/MagicStack/uvloop)
- [python-websockets](https://github.com/python-websockets/websockets)
- [kalshi-python (Official)](https://pypi.org/project/kalshi-python/)
- [kalshi-python-unofficial](https://github.com/humz2k/kalshi-python-unofficial)

### Performance Research
- [Connection Pooling - 70% Latency Reduction](https://www.marketcalls.in/python/slashing-api-order-latency-upto-70-with-http-connection-pooling.html)
- [aiohttp vs httpx Performance](https://oxylabs.io/blog/httpx-vs-requests-vs-aiohttp)
- [Python HFT Low-Latency Techniques](https://www.pyquantnews.com/free-python-resources/python-in-high-frequency-trading-low-latency-techniques)

### Infrastructure
- [QuantVPS Kalshi VPS](https://www.quantvps.com/kalshi-vps)

---

## Summary

The biggest wins come from:
1. **Persistent connection pooling** - Stop creating new sessions (40% improvement)
2. **WebSocket streaming** - Real-time data instead of polling (60%+ improvement)
3. **uvloop** - Faster event loop (25% improvement)

These three changes alone should get us from 2,200ms to <500ms - well over the 50% reduction target.
