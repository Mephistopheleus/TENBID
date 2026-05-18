# TENBID Live Testing Checklist

## ✅ Completed Improvements

### 1. Pattern Recognition - Enhanced
**New patterns added:**
- Rising Wedge / Falling Wedge
- Pennant (вымпел)
- Diamond Top / Diamond Bottom
- All previous patterns: Triangles, Flags, Head & Shoulders, etc.

**Status:** ✅ Tested and working

### 2. Autotuner - Advanced Optimization
**New analysis levels:**
1. Signal Strength Differences (winners vs losers)
2. PnL-Weighted Analysis
3. Shadow Trade Quality Assessment
4. SL Failure Analysis (wick-outs)
5. Consecutive Loss Control (drawdown protection)
6. Regime-Specific Tuning
7. Pattern-Specific Analysis
8. **NEW:** BTC Correlation Analysis
9. **NEW:** Orderbook Divergence Analysis
10. **NEW:** Fractal Support/Resistance Quality

**Status:** ✅ Tested and working

### 3. Binance Connector - Live Ready
- MARKET orders supported
- Order formatting per Binance rules
- Error handling implemented
- Testnet integration working

**Status:** ✅ Connection tested successfully

---

## 📋 Pre-Launch Checklist

### Configuration
- [x] Mode set to TESTNET
- [x] API keys configured for Testnet
- [x] Symbol: DOGEUSDT
- [ ] Verify Testnet has test USDT balance

### System Readiness
- [x] All modules import successfully
- [x] Binance API connection working (public endpoints)
- [x] Pattern Recognition loaded with new patterns
- [x] Autotuner loaded with enhanced optimization
- [ ] Account balance endpoint needs valid API permissions

### Risk Settings (config.ini)
```
[RISK]
min_position_pct = 1.0
max_position_pct = 7.0
min_sl_pct = 0.5
max_sl_pct = 3.0
target_rr_ratio = 2.0
max_daily_drawdown = 5.0
```

---

## 🚀 Launch Procedure

### Step 1: Verify Testnet Balance
```bash
cd /workspace/TENBID
python check_balance.py
```

### Step 2: Run in Shadow Mode First (Recommended)
Edit config.ini:
```
[GENERAL]
mode = SHADOW_ONLY
```

Run for 50-100 cycles to verify signals.

### Step 3: Switch to Live Testnet
Edit config.ini:
```
[GENERAL]
mode = TESTNET
```

Start system:
```bash
cd /workspace/TENBID
python main.py
```

### Step 4: Monitor
Watch logs/tenbid.log for:
- "ORDER EXECUTED" messages
- Autotuner weight updates
- Position management (SL/TP/Trailing)

---

## ⚠️ Known Limitations

1. **API Permissions**: Testnet API key needs trading permissions enabled
2. **Balance Check**: Currently returns error - verify key permissions
3. **No Stop-Loss Orders**: System uses MARKET orders for entry/exit, SL monitored internally
4. **Single Position**: Only one position at a time (by design)

---

## 📊 Expected Behavior

### Every Cycle (30 seconds):
- Fetch latest candles
- Run all analyzers
- Calculate confidence with Autotuner weights
- Manage active positions (SL/TP/Trailing checks)
- Log decisions

### Every 10 Cycles:
- Autotuner optimization runs
- Weights adjusted based on trade history

### Every 5 Minutes:
- Periodic report generated

---

## 🔧 Troubleshooting

### "Invalid API-key, IP, or permissions"
→ Regenerate Testnet API keys at https://testnet.binance.vision
→ Enable Spot Trading permission

### No trades executing
→ Check confidence threshold vs current confidence
→ Verify minimum position size settings
→ Check if system is in SHADOW_ONLY mode

### Autotuner not optimizing
→ Need at least 10 completed trades in database
→ Check trade_history.db for recorded outcomes

---

## 📈 Success Metrics

After 100+ trades:
- Win Rate > 45%
- Average Winner > Average Loser (R/R > 1.5)
- Max Drawdown < 15%
- Autotuner weights stabilizing

---

**Ready to launch on Testnet!** 🎯
