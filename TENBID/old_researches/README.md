# Old Research Modules

This directory contains archived trading modules from previous research iterations.

## Archived Modules

### position_sizer.py
**Date Archived:** 2026-05-30
**Reason:** Replaced by `core/trade_calculator.py`

**Old Approach:**
- Decision based on `confidence` score (0.5-1.0)
- Simple ATR-based SL calculation
- Regime and pattern adjustments
- Data quality factor

**Why Replaced:**
- New system uses probability matrix instead of confidence scores
- TradeCalculator provides full trade analysis with cost calculation
- Better integration with granular trust system
- More sophisticated decision logic (OPEN/HOLD based on matrix zones)

---

### smart_trailing.py
**Date Archived:** 2026-05-30
**Reason:** Replaced by `trading/adaptive_trailing.py`

**Old Approach:**
- ATR-based trailing stop
- Regime-based adjustments (volatile/ranging/trending)
- Pattern-based tightening
- Fixed activation threshold

**Why Replaced:**
- New system uses probability matrix forecasts
- AdaptiveTrailing analyzes future price movement predictions
- Priority-based logic: breakeven first, then adaptive trailing
- Aggressive/conservative modes based on forecast direction
- Better integration with autotuner parameters

---

## Historical Context

These modules were part of the confidence-based trading system. The new matrix-based system provides:

1. **Granular Trust:** analyzer + timeframe + metric + regime
2. **Probability Matrix:** Grid + Gaussian Blur for forecast aggregation
3. **Full Cost Analysis:** commission + spread + slippage
4. **Adaptive Behavior:** based on real-time market forecasts
5. **Autotuner Integration:** all parameters optimized for 100WR/100PnL/0DD

## Usage

These files are kept for:
- Historical reference
- Research comparison
- Documentation purposes
- Potential future analysis

**Do not use in production.** The active system uses the new matrix-based modules.
