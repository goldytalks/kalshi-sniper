# Kalshi Sniper

Automated stale order detection and execution system for Kalshi prediction markets. Exploits the lag between live game moneyline (ML) price movements and correlated market adjustments.

## Strategy Overview

When a significant event happens in a live game (touchdown, basket, etc.), courtsiders instantly update the ML market. However, market makers on correlated markets (totals, spreads, props) are slower to adjust their orders. This creates a window where "stale" orders can be hit for profit.

**The Edge:**
- ML markets update in <1 second (courtsiders at the game)
- Correlated markets take 5-60 seconds to adjust
- Automated bot can capture opportunities faster than manual trading

## Backtest Results (January 4, 2026)

### All Games Summary
| Metric | Value |
|--------|-------|
| Games analyzed | 10 (NFL + NBA) |
| Total opportunities | 23,882 |
| Total theoretical edge | $10,424 |
| Realistic profit (800ms bot) | **$6,266** |

### By Sport
| Sport | Opportunities | Total Edge | Avg Edge |
|-------|---------------|------------|----------|
| NFL | 18,002 | $8,630 | 47.9¢ |
| NBA | 5,880 | $1,794 | 30.5¢ |

### By Market Type
| Type | Opportunities | Total Edge | Avg Edge |
|------|---------------|------------|----------|
| Totals | 17,919 (75%) | $8,180 | 45.7¢ |
| Spreads | 4,409 (18%) | $1,673 | 37.9¢ |
| TD Props | 1,554 (7%) | $571 | 36.7¢ |

### Opportunity Decay (How Fast They Disappear)
| Lag Time | % of Opps | Avg Edge |
|----------|-----------|----------|
| 0-1 sec | 3% | 49.0¢ |
| 1-5 sec | 8% | 45.8¢ |
| 5-15 sec | 20% | 44.9¢ |
| 15-30 sec | 26% | 46.4¢ |
| 30-60 sec | 43% | 40.6¢ |

### Profit by Execution Speed
| Speed | Capture Rate | NET PROFIT (per day) |
|-------|--------------|----------------------|
| Manual (3-5s) | 10% | $1,852 |
| Slow bot (2s) | 15% | $2,748 |
| **Medium bot (800ms)** | **40%** | **$6,266** |
| Fast bot (300ms) | 60% | $8,155 |

## Files

### Core Trading
- **`fast_sniper.py`** - Production bot with async parallel execution (~800ms latency)
- **`live_sniper.py`** - Simpler REST-based sniper
- **`kalshi_api.py`** - API wrapper with RSA-PSS authentication

### Backtesting
- **`full_backtest_jan4.py`** - Comprehensive backtest across all sports
- **`backtest_jan4_nfl.py`** - NFL-specific detailed backtest
- **`comprehensive_backtest.py`** - Multi-market correlation analysis
- **`backtest_nba.py`** - NBA market analysis

### Analysis & Discovery
- **`find_all_active_sports.py`** - Discover all active sports markets
- **`find_all_correlated.py`** - Map ML to correlated markets
- **`test_execution_speed.py`** - Benchmark API latency

### Risk Management
- **`risk_management.py`** - Position sizing and risk controls

## Setup

### 1. API Credentials
Create `~/.kalshi/config.json`:
```json
{
    "api_key_id": "your-api-key-id",
    "private_key_path": "/path/to/private_key.pem"
}
```

### 2. Install Dependencies
```bash
pip install requests aiohttp websockets cryptography
```

### 3. Run Speed Test
```bash
python fast_sniper.py --test
```

### 4. Run Live (Simulation)
```bash
python fast_sniper.py --sport NFL
```

### 5. Run Live (Execute Trades)
```bash
python fast_sniper.py --sport NFL --execute --max-position 50
```

## Usage

### Fast Sniper (Recommended)
```bash
# Test speed
python fast_sniper.py --test

# Monitor NFL (simulation)
python fast_sniper.py --sport NFL

# Monitor all sports (simulation)
python fast_sniper.py --sport ALL

# Live execution
python fast_sniper.py --sport NFL --execute --min-edge 10 --max-position 50
```

### Backtest
```bash
# Full backtest
python full_backtest_jan4.py

# NFL only
python backtest_jan4_nfl.py
```

## Capital Requirements

| Bankroll | Strategy | Expected Profit/Game |
|----------|----------|---------------------|
| $500 | Conservative (>20¢ edge) | $50-100 |
| $1,000 | Moderate (>10¢ edge) | $100-200 |
| $2,500 | Aggressive (>5¢ edge) | $200-400 |

**Why $500-1,000 is enough:**
- Kalshi has position limits per market
- Stale orders have limited liquidity
- Better to be fast than big

## Key Insights

1. **Totals markets are most inefficient** - 75% of all opportunities
2. **NFL has bigger edges than NBA** - 48¢ vs 30¢ average
3. **Speed matters exponentially** - 800ms bot captures 4x more than manual
4. **43% of opportunities last 30-60 seconds** - Even slow bots can profit
5. **High-edge opportunities (>50¢) disappear fastest** - Need speed for best trades

## Risk Controls

- **Max position per trade:** $50-100
- **Daily loss limit:** $100 (stop and review)
- **Minimum edge:** 8¢ after fees
- **Max lag:** 45 seconds (older = likely filled)

## Fees

Kalshi charges 7% of profits on winning trades:
- No fee on losing trades
- Example: 30¢ edge → ~2¢ fee → 28¢ net

## Limitations

1. **Competition** - Other bots are doing this too
2. **Liquidity** - Stale orders are finite
3. **Execution** - Orders can fail or partial fill
4. **Edge decay** - Market makers will adapt over time

## License

Private use only. Not financial advice.
