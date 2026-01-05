"""
Risk Management Framework for $500 Kalshi Sniper

Position sizing, loss limits, and execution rules based on backtest findings.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

class RiskManager:
    def __init__(self, bankroll=500):
        self.initial_bankroll = bankroll
        self.current_bankroll = bankroll
        self.daily_loss_limit = 100  # Stop trading if down $100 in a day
        self.max_position_per_trade = 50  # Max $50 per trade
        self.min_edge_cents = 5  # Minimum edge after fees to trade
        self.kalshi_fee_rate = 0.07  # 7% of winnings (only on wins)

        # Track performance
        self.trades = []
        self.daily_pnl = 0
        self.session_start = datetime.now()
        self.trade_count_today = 0

        # Backtest-derived parameters
        self.optimal_thresholds = {
            "ml_move_trigger": 5,  # cents - trigger on 5+ cent ML move
            "max_lag_seconds": 45,  # seconds - only trade if stale order detected within 45s
            "min_volume": 50000,   # $ - only trade markets with >$50k volume
        }

    def calculate_position_size(self, edge_cents, confidence="medium"):
        """
        Kelly Criterion-inspired position sizing.

        Based on backtest: avg edge ~19 cents, win rate ~65% (estimate)
        Full Kelly = edge/odds, but we use 1/4 Kelly for safety.

        Args:
            edge_cents: Expected edge in cents
            confidence: "high", "medium", "low" based on signal quality

        Returns:
            Position size in dollars
        """
        # Confidence multipliers
        confidence_mult = {"high": 1.0, "medium": 0.5, "low": 0.25}
        mult = confidence_mult.get(confidence, 0.5)

        # Base position: 2% of bankroll per trade (conservative)
        base_position = self.current_bankroll * 0.02

        # Scale by edge size (more edge = bigger position)
        # Normalize: 5 cent edge = base, 20 cent edge = 2x base
        edge_multiplier = min(edge_cents / 10, 2.0)  # Cap at 2x

        # Calculate position
        position = base_position * edge_multiplier * mult

        # Apply limits
        position = min(position, self.max_position_per_trade)
        position = min(position, self.current_bankroll * 0.1)  # Never more than 10% of bankroll
        position = max(position, 1)  # Minimum $1

        return round(position, 2)

    def check_can_trade(self):
        """
        Pre-trade risk checks.

        Returns:
            (can_trade: bool, reason: str)
        """
        # Check daily loss limit
        if self.daily_pnl <= -self.daily_loss_limit:
            return False, f"Daily loss limit hit (${-self.daily_pnl})"

        # Check bankroll
        if self.current_bankroll < 10:
            return False, "Bankroll too low (<$10)"

        # Check trade frequency (max 50 trades per day)
        if self.trade_count_today >= 50:
            return False, "Daily trade limit reached (50)"

        return True, "OK"

    def evaluate_opportunity(self, opportunity):
        """
        Evaluate if an opportunity is worth trading.

        Args:
            opportunity: dict with keys: edge, lag_sec, volume, market_type

        Returns:
            (should_trade: bool, position_size: int, reason: str)
        """
        edge = opportunity.get("edge", 0)
        lag = opportunity.get("lag_sec", 999)
        volume = opportunity.get("volume", 0)

        # Check basic thresholds
        if edge < self.min_edge_cents:
            return False, 0, f"Edge too small ({edge}c < {self.min_edge_cents}c min)"

        if lag > self.optimal_thresholds["max_lag_seconds"]:
            return False, 0, f"Stale order too old ({lag}s > {self.optimal_thresholds['max_lag_seconds']}s)"

        if volume < self.optimal_thresholds["min_volume"]:
            return False, 0, f"Volume too low (${volume:,} < ${self.optimal_thresholds['min_volume']:,})"

        # Check global risk limits
        can_trade, reason = self.check_can_trade()
        if not can_trade:
            return False, 0, reason

        # Determine confidence based on signal quality
        confidence = "medium"
        if edge >= 15 and lag <= 15:
            confidence = "high"
        elif edge < 8 or lag > 30:
            confidence = "low"

        position = self.calculate_position_size(edge, confidence)

        return True, position, f"Trade approved: {confidence} confidence, ${position}"

    def record_trade(self, trade_result):
        """
        Record a completed trade and update tracking.

        Args:
            trade_result: dict with keys: pnl, edge, position, market, timestamp
        """
        self.trades.append(trade_result)
        pnl = trade_result.get("pnl", 0)
        self.daily_pnl += pnl
        self.current_bankroll += pnl
        self.trade_count_today += 1

    def calculate_expected_value(self, edge_cents, position_dollars):
        """
        Calculate expected value of a trade after fees.

        Kalshi charges ~7% of winnings (no fee on losses).
        Edge already accounts for price difference, but we need to factor fees.
        """
        # Probability implied by edge (rough approximation)
        # If we have 10 cent edge on 50/50 market, we're getting 40 for something worth 50
        # Win rate = (100 - price) / 100 for a YES trade

        # Simplified: edge * position / 100, minus fees on wins
        gross_ev = (edge_cents / 100) * position_dollars
        estimated_fee = gross_ev * 0.5 * self.kalshi_fee_rate  # ~50% win rate, fee only on wins
        net_ev = gross_ev - estimated_fee

        return round(net_ev, 2)

    def get_status(self):
        """Get current risk management status."""
        return {
            "bankroll": self.current_bankroll,
            "initial_bankroll": self.initial_bankroll,
            "pnl_total": self.current_bankroll - self.initial_bankroll,
            "pnl_today": self.daily_pnl,
            "trades_today": self.trade_count_today,
            "trades_total": len(self.trades),
            "can_trade": self.check_can_trade()[0],
            "daily_loss_remaining": self.daily_loss_limit + self.daily_pnl,
        }

    def reset_daily(self):
        """Reset daily counters (call at start of new trading day)."""
        self.daily_pnl = 0
        self.trade_count_today = 0
        self.session_start = datetime.now()

    def print_summary(self):
        """Print risk management summary."""
        status = self.get_status()
        print("\n" + "="*60)
        print("RISK MANAGEMENT STATUS")
        print("="*60)
        print(f"Bankroll: ${status['bankroll']:.2f} (started: ${status['initial_bankroll']})")
        print(f"Total P&L: ${status['pnl_total']:.2f}")
        print(f"Today's P&L: ${status['pnl_today']:.2f}")
        print(f"Trades today: {status['trades_today']} / 50 max")
        print(f"Daily loss remaining: ${status['daily_loss_remaining']:.2f}")
        print(f"Can trade: {'Yes' if status['can_trade'] else 'NO - BLOCKED'}")
        print("="*60)


# Position sizing table for quick reference
POSITION_SIZING_TABLE = """
POSITION SIZING GUIDE ($500 bankroll)
=====================================

Edge (cents) | Confidence | Position ($) | Expected Value
-------------|------------|--------------|---------------
5-7          | Low        | $2-3         | $0.08-0.15
5-7          | Medium     | $4-5         | $0.15-0.25
8-12         | Low        | $3-4         | $0.20-0.35
8-12         | Medium     | $6-8         | $0.40-0.70
8-12         | High       | $10-12       | $0.65-1.00
13-20        | Medium     | $10-15       | $1.00-2.25
13-20        | High       | $20-25       | $2.00-3.75
20+          | High       | $30-50       | $4.00-8.00

Confidence Criteria:
- High: Edge >15c AND lag <15s AND high volume
- Medium: Edge 8-15c OR lag 15-30s
- Low: Edge <8c OR lag >30s OR low volume

Risk Rules:
- Max 10% bankroll per trade ($50)
- Daily loss limit: $100 (stop trading)
- Min edge: 5 cents (after ~3c fees = 2c net)
- Max lag: 45 seconds (stale order likely filled)
"""


# Backtest-derived insights
BACKTEST_INSIGHTS = """
BACKTEST INSIGHTS (NFL Ravens-Steelers Game)
=============================================

Market Performance:
1. TOTALS MARKETS - Best opportunity
   - 152 opportunities found
   - 2,860 cents total edge
   - 25.1s average lag (tradeable)
   - Avg 18.8 cent edge per trade

2. TOUCHDOWN PROPS - High edge, fewer opportunities
   - 42 opportunities
   - 1,089 cents total edge
   - 40.6s average lag
   - Avg 25.9 cent edge per trade

3. DIVISION MARKETS - Faster, smaller edge
   - 36 opportunities
   - 523 cents total edge
   - 10.3s average lag
   - Avg 14.5 cent edge per trade

Key Findings:
- Stale orders exist and are tradeable
- 10-45 second window to capture
- Higher edge on less liquid markets (props)
- Faster execution needed for division markets
- ~19 cent average edge across all types
- After 3 cent fees, ~16 cent net edge

Expected Performance ($500 bankroll, conservative):
- 10-20 trades per game
- $0.50-2.00 net profit per trade
- $5-40 profit per primetime game
- 4 primetime games/week = $20-160/week potential
"""


if __name__ == "__main__":
    # Demo the risk manager
    rm = RiskManager(bankroll=500)

    print(POSITION_SIZING_TABLE)
    print(BACKTEST_INSIGHTS)

    # Test opportunity evaluation
    print("\n" + "="*60)
    print("TEST OPPORTUNITY EVALUATIONS")
    print("="*60)

    test_opportunities = [
        {"edge": 15, "lag_sec": 20, "volume": 500000, "market": "Totals Over 40"},
        {"edge": 8, "lag_sec": 45, "volume": 100000, "market": "AFC North"},
        {"edge": 25, "lag_sec": 10, "volume": 200000, "market": "Anytime TD"},
        {"edge": 4, "lag_sec": 5, "volume": 1000000, "market": "Game ML"},  # Edge too small
        {"edge": 10, "lag_sec": 60, "volume": 50000, "market": "Team Total"},  # Lag too high
    ]

    for opp in test_opportunities:
        should_trade, position, reason = rm.evaluate_opportunity(opp)
        ev = rm.calculate_expected_value(opp["edge"], position) if should_trade else 0
        print(f"\n{opp['market']}:")
        print(f"  Edge: {opp['edge']}c | Lag: {opp['lag_sec']}s | Volume: ${opp['volume']:,}")
        print(f"  Decision: {'TRADE' if should_trade else 'SKIP'}")
        print(f"  Position: ${position} | EV: ${ev:.2f}")
        print(f"  Reason: {reason}")

    rm.print_summary()
