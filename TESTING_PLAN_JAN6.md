# Testing Plan: January 6, 2026

## Today's Games Overview

### NBA Games (6 games) - PRIMARY FOCUS
| Game | Time (ET) | Best For Testing |
|------|-----------|------------------|
| Cavaliers @ Pacers | 7:00 PM | Good - competitive matchup |
| Magic @ Wizards | 7:00 PM | Lower volume expected |
| Spurs @ Grizzlies | 8:00 PM | Good - Wemby factor |
| Lakers @ Pelicans | 8:00 PM | **HIGH** - Lakers = high volume |
| Heat @ Timberwolves | 8:00 PM | **NBC** - nationally televised |
| Mavericks @ Kings | 11:00 PM | **NBC** - Luka vs De'Aaron |

### NHL Games (10 games) - SECONDARY
| Game | Time (ET) | Notes |
|------|-----------|-------|
| Canucks @ Sabres | 7:00 PM | |
| Avalanche @ Lightning | 7:00 PM | High-profile matchup |
| Ducks @ Flyers | 7:00 PM | |
| Stars @ Hurricanes | 7:00 PM | |
| Devils @ Islanders | 7:30 PM | |
| Panthers @ Maple Leafs | 7:30 PM | **HIGH** - big market |
| Golden Knights @ Jets | 8:00 PM | |
| Predators @ Oilers | 9:00 PM | McDavid factor |
| Blue Jackets @ Sharks | 10:00 PM | |
| Bruins @ Kraken | 10:00 PM | |

### NFL - NO GAMES TODAY
Wild Card Weekend starts **January 10-12, 2026**

### College Basketball (~19 games)
Multiple games available - lower liquidity but more opportunities

---

## Recommended Testing Schedule

### Phase 1: Pre-Game Setup (5:00 - 6:30 PM ET)

1. **Configure API Credentials**
   ```bash
   mkdir -p ~/.kalshi
   # Create config.json with your API key
   ```

2. **Test API Connection**
   ```bash
   python kalshi_api.py
   ```

3. **Discover Today's Markets**
   ```bash
   python find_all_active_sports.py
   ```
   - Note: Without credentials, this won't run. Once you have credentials, run this to see all active markets.

4. **Run Speed Test**
   ```bash
   python fast_sniper.py --test
   ```
   - Baseline your latency before games start
   - Target: <2.5s (current), ideally <1s (optimized)

### Phase 2: Early Games Simulation (7:00 - 8:00 PM ET)

**Target Games:**
- Cavaliers @ Pacers (7:00 PM)
- Magic @ Wizards (7:00 PM)
- NHL: Panthers @ Maple Leafs (7:30 PM)

**Run in Simulation Mode:**
```bash
python fast_sniper.py --sport NBA --min-edge 10 --interval 0.5
```

**What to Watch:**
- ML price movements when scores change
- How quickly correlated markets (totals, spreads) update
- Number of stale order opportunities detected
- Your latency stats

### Phase 3: Prime Time Testing (8:00 - 10:00 PM ET)

**High-Volume Games (Best for Testing):**
- Lakers @ Pelicans (8:00 PM) - LeBron = high volume
- Heat @ Timberwolves (8:00 PM) - NBC nationally televised
- Spurs @ Grizzlies (8:00 PM) - Wembanyama factor

**Run Multi-Sport:**
```bash
python fast_sniper.py --sport ALL --min-edge 8 --interval 0.3
```

**Key Metrics to Track:**
- Opportunities per game
- Average edge detected
- Lag time between ML move and stale order
- Execution speed (detection → alert)

### Phase 4: Late Game + Analysis (10:00 PM - 12:00 AM ET)

**Late Game:**
- Mavericks @ Kings (11:00 PM) - NBC, high profile

**If Comfortable, Try Small Live Execution:**
```bash
python fast_sniper.py --sport NBA --execute --min-edge 15 --max-position 25
```
- Start with **high edge threshold** (15¢+)
- Start with **small positions** ($25 max)
- Watch 2-3 opportunities before scaling up

---

## What to Monitor During Testing

### Per-Opportunity Metrics
| Metric | What to Look For |
|--------|-----------------|
| ML Move Size | 5¢+ triggers our detection |
| Lag Time | How long stale orders persist |
| Edge Size | Bigger = more confidence |
| Liquidity | Can we actually fill? |

### System Metrics
| Metric | Target | Current |
|--------|--------|---------|
| Detection Latency | <500ms | ~2,200ms |
| Orderbook Fetch | <300ms | ~365ms |
| End-to-End | <1,000ms | ~2,200ms |

### Expected Results (Based on Backtest)
| Scenario | Opportunities | Edge |
|----------|---------------|------|
| 6 NBA games | 800-1,200 | $300-500 |
| Including NHL | 1,000-1,500 | $400-600 |
| Full day | 1,500-2,000 | $500-800 |

---

## Pre-Flight Checklist

### Required
- [ ] Kalshi account created
- [ ] API key generated
- [ ] Private key (.pem) downloaded
- [ ] `~/.kalshi/config.json` configured
- [ ] Python dependencies installed (`pip install requests aiohttp websockets cryptography`)
- [ ] API connection test passes

### Recommended
- [ ] $500+ in Kalshi account (for live testing)
- [ ] Second monitor for game streams
- [ ] Note-taking for observations

---

## Risk Controls for Live Testing

### Conservative Settings (First Time)
```bash
python fast_sniper.py --sport NBA --execute \
  --min-edge 15 \      # Only take 15¢+ edge
  --max-position 25    # Max $25 per trade
```

### Standard Settings (After Validation)
```bash
python fast_sniper.py --sport NBA --execute \
  --min-edge 10 \      # 10¢+ edge
  --max-position 50    # Max $50 per trade
```

### Aggressive Settings (Confident)
```bash
python fast_sniper.py --sport ALL --execute \
  --min-edge 8 \       # 8¢+ edge
  --max-position 100   # Max $100 per trade
```

---

## Expected Timeline

| Time (ET) | Activity |
|-----------|----------|
| 5:00 PM | Setup & configuration |
| 6:00 PM | Speed test & market discovery |
| 7:00 PM | Start simulation (early NBA + NHL) |
| 8:00 PM | Prime time monitoring |
| 9:00 PM | Review stats, consider live execution |
| 10:00 PM | Late games, continued monitoring |
| 11:00 PM | Mavericks @ Kings (NBC) |
| 12:00 AM | End of day analysis |

---

## Post-Testing Analysis

After testing, review:

1. **Log Files**: `fast_sniper_log_*.json`
2. **Key Questions**:
   - How many opportunities detected?
   - What was average edge?
   - How many could we have captured at our speed?
   - Any failed executions?
3. **Compare to Backtest**:
   - Did we see similar opportunity rates?
   - Was edge size consistent?
   - Any market behavior surprises?

---

## Quick Start Commands

```bash
# 1. Test connection
python kalshi_api.py

# 2. Find active markets
python find_all_active_sports.py

# 3. Speed test
python fast_sniper.py --test

# 4. Simulation mode (NBA only)
python fast_sniper.py --sport NBA

# 5. Simulation mode (all sports)
python fast_sniper.py --sport ALL

# 6. Live execution (conservative)
python fast_sniper.py --sport NBA --execute --min-edge 15 --max-position 25
```

---

## Notes

- **No NFL today** - Wild Card starts Jan 10-12
- **Best opportunities**: Lakers/Pelicans, Heat/Timberwolves (NBC games)
- **NHL bonus**: 10 games = more opportunities if NBA is slow
- **Start conservative**: High edge threshold, small positions
- **Document everything**: Take notes on what you observe

Good luck!
