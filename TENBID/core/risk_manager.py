"""
Risk Manager - Dynamic Position Sizing and Drawdown Protection.

CRITICAL REQUIREMENTS:
1. NO fixed percentages - risk calculated dynamically: Balance * Risk% / |Entry - SL|
2. Dynamic concurrent trade limit based on drawdown and winrate history
3. Activity Factor reduces risk during drawdowns
4. Protection from ZeroDivisionError and NaN in all calculations
"""

import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class RiskParameters:
    """Calculated risk parameters for a trade."""
    position_size: float  # In quote currency (USDT)
    leverage: int  # Adaptive leverage (1x - 20x)
    stop_loss_price: float
    take_profit_price: float
    risk_percent: float  # Actual risk % of balance
    max_concurrent_trades: int  # Current limit based on drawdown
    activity_factor: float  # 0.0 to 1.0, reduces risk during drawdown
    
@dataclass
class AccountState:
    """Current account state for risk calculations."""
    balance: float
    equity: float
    unrealized_pnl: float
    open_positions_count: int
    total_position_value: float
    daily_pnl: float
    max_drawdown_percent: float  # From peak equity

class RiskManager:
    def __init__(
        self,
        base_risk_percent: float = 1.0,
        max_risk_percent: float = 3.0,
        min_risk_percent: float = 0.5,
        default_leverage: int = 5,
        max_leverage: int = 20
    ):
        """
        Initialize Risk Manager with dynamic risk controls.
        
        Args:
            base_risk_percent: Base risk per trade (default 1%)
            max_risk_percent: Maximum risk in optimal conditions
            min_risk_percent: Minimum risk during high drawdown
            default_leverage: Starting leverage
            max_leverage: Maximum allowed leverage
        """
        self.base_risk_percent = base_risk_percent
        self.max_risk_percent = max_risk_percent
        self.min_risk_percent = min_risk_percent
        self.default_leverage = default_leverage
        self.max_leverage = max_leverage
        
        # CRITICAL: Default ATR floor to prevent division by zero
        self.MIN_ATR = 0.0001
        self.MIN_PRICE_DIFF = 0.0001
        
        # Drawdown thresholds for activity reduction
        self.DRAWDOWN_THRESHOLDS = {
            5.0: 0.8,    # 5% DD -> 80% activity
            10.0: 0.5,   # 10% DD -> 50% activity
            15.0: 0.3,   # 15% DD -> 30% activity
            20.0: 0.1    # 20% DD -> 10% activity (emergency mode)
        }
        
        # Dynamic concurrent trade limits
        self.base_max_trades = 3
        self.min_max_trades = 1
        
        logger.info(f"RiskManager initialized: base_risk={base_risk_percent}%, max_leverage={max_leverage}x")
    
    def calculate_position_size(
        self,
        account: AccountState,
        entry_price: float,
        stop_loss_price: float,
        atr: float = 0.0,
        confidence: float = 0.5,
        regime_type: str = 'NORMAL'
    ) -> RiskParameters:
        """
        CRITICAL: Calculate position size using dynamic risk formula.
        
        Formula: Position Size = (Balance * Risk%) / |Entry - SL|
        
        Includes:
        - Activity Factor based on drawdown
        - ATR-based SL adjustment if provided
        - Confidence-based leverage adjustment
        - Regime-based risk adjustment
        """
        # Calculate current drawdown
        drawdown = account.max_drawdown_percent
        
        # Get Activity Factor based on drawdown
        activity_factor = self._calculate_activity_factor(drawdown)
        
        # Adjust risk percent based on activity factor and confidence
        adjusted_risk = self._calculate_adjusted_risk(
            base_risk=self.base_risk_percent,
            activity_factor=activity_factor,
            confidence=confidence,
            regime_type=regime_type
        )
        
        # Calculate price difference (CRITICAL: protect from zero)
        price_diff = abs(entry_price - stop_loss_price)
        if price_diff < self.MIN_PRICE_DIFF:
            logger.warning(f"SL distance too small ({price_diff}), using minimum")
            price_diff = self.MIN_PRICE_DIFF
        
        # Calculate position size: (Balance * Risk%) / Price_Diff
        # This gives us the position size where loss = Risk% of balance if SL hits
        raw_position_size = (account.balance * adjusted_risk / 100) / price_diff
        
        # Convert to quote currency (position_size * entry_price)
        position_size_quote = raw_position_size * entry_price
        
        # Clamp position size to reasonable bounds
        min_position = account.balance * 0.01  # Minimum 1% of balance
        max_position = account.balance * self.max_risk_percent * 10  # Max exposure
        
        position_size_quote = max(min_position, min(max_position, position_size_quote))
        
        # Calculate adaptive leverage
        leverage = self._calculate_adaptive_leverage(
            confidence=confidence,
            volatility=atr / entry_price if entry_price > 0 and atr > 0 else 0.01,
            drawdown=drawdown,
            regime_type=regime_type
        )
        
        # Calculate actual risk percent
        actual_risk = (position_size_quote * price_diff / entry_price) / account.balance * 100
        
        # Determine max concurrent trades based on drawdown
        max_concurrent = self._calculate_max_concurrent_trades(drawdown, account.daily_pnl)
        
        # Calculate TP (typically 2:1 or 3:1 reward:risk)
        risk_reward_ratio = 2.5 if regime_type == 'STRONG_TREND' else 2.0
        tp_distance = price_diff * risk_reward_ratio
        
        if entry_price > stop_loss_price:  # Long
            take_profit_price = entry_price + tp_distance
        else:  # Short
            take_profit_price = entry_price - tp_distance
        
        return RiskParameters(
            position_size=round(position_size_quote, 2),
            leverage=leverage,
            stop_loss_price=round(stop_loss_price, 8),
            take_profit_price=round(take_profit_price, 8),
            risk_percent=round(actual_risk, 4),
            max_concurrent_trades=max_concurrent,
            activity_factor=round(activity_factor, 3)
        )
    
    def _calculate_activity_factor(self, drawdown: float) -> float:
        """
        Calculate activity factor based on current drawdown.
        
        Reduces trading activity as drawdown increases.
        """
        if drawdown <= 0:
            return 1.0
        
        # Find appropriate threshold
        for dd_threshold, factor in sorted(self.DRAWDOWN_THRESHOLDS.items()):
            if drawdown >= dd_threshold:
                return factor
        
        # Linear interpolation for values between thresholds
        return 1.0 - (drawdown / 25.0)  # Gradual reduction
    
    def _calculate_adjusted_risk(
        self,
        base_risk: float,
        activity_factor: float,
        confidence: float,
        regime_type: str
    ) -> float:
        """
        Calculate adjusted risk percent based on multiple factors.
        """
        # Start with base risk
        risk = base_risk
        
        # Apply activity factor (drawdown protection)
        risk *= activity_factor
        
        # Adjust for confidence (higher confidence = slightly higher risk)
        confidence_multiplier = 0.8 + (confidence * 0.4)  # 0.8 to 1.2
        risk *= confidence_multiplier
        
        # Adjust for regime
        if regime_type == 'RANGING':
            risk *= 0.7  # Reduce risk in choppy markets
        elif regime_type == 'STRONG_TREND':
            risk *= 1.3  # Increase risk in clear trends
        elif regime_type == 'HIGH_VOLATILITY':
            risk *= 0.6  # Reduce risk in volatile markets
        
        # Clamp to min/max bounds
        risk = max(self.min_risk_percent, min(self.max_risk_percent, risk))
        
        return risk
    
    def _calculate_adaptive_leverage(
        self,
        confidence: float,
        volatility: float,
        drawdown: float,
        regime_type: str
    ) -> int:
        """
        Calculate adaptive leverage based on market conditions.
        
        Leverage increases with:
        - High confidence (>80%)
        - Low volatility
        - Clear trend regime
        
        Leverage decreases with:
        - Low confidence
        - High volatility
        - High drawdown
        - Ranging market
        """
        # Start with default leverage
        leverage = self.default_leverage
        
        # Confidence adjustment
        if confidence > 0.8:
            leverage = min(self.max_leverage, leverage + 3)
        elif confidence > 0.6:
            leverage = min(self.max_leverage, leverage + 1)
        elif confidence < 0.4:
            leverage = max(1, leverage - 2)
        
        # Volatility adjustment (inverse relationship)
        if volatility > 0.05:  # >5% ATR
            leverage = max(1, leverage - 3)
        elif volatility > 0.03:
            leverage = max(1, leverage - 1)
        
        # Regime adjustment
        if regime_type == 'RANGING':
            leverage = max(1, leverage - 2)
        elif regime_type == 'STRONG_TREND':
            leverage = min(self.max_leverage, leverage + 2)
        elif regime_type == 'HIGH_VOLATILITY':
            leverage = max(1, leverage - 2)
        
        # Drawdown adjustment (critical protection)
        if drawdown > 10:
            leverage = max(1, leverage - 3)
        elif drawdown > 5:
            leverage = max(1, leverage - 1)
        
        # Ensure leverage is at least 1x and at most max_leverage
        leverage = max(1, min(self.max_leverage, leverage))
        
        return leverage
    
    def _calculate_max_concurrent_trades(
        self,
        drawdown: float,
        daily_pnl: float
    ) -> int:
        """
        Calculate maximum concurrent trades based on account state.
        
        This is a DYNAMIC parameter that changes with performance.
        """
        # Start with base limit
        max_trades = self.base_max_trades
        
        # Reduce on drawdown
        if drawdown > 15:
            max_trades = self.min_max_trades
        elif drawdown > 10:
            max_trades = max(self.min_max_trades, 2)
        elif drawdown > 5:
            max_trades = max(self.min_max_trades, self.base_max_trades - 1)
        
        # Reduce on losing day
        if daily_pnl < -5:  # Down more than 5% today
            max_trades = max(self.min_max_trades, max_trades - 1)
        
        # Can increase on winning streak (but capped)
        if daily_pnl > 5 and drawdown < 5:
            max_trades = min(self.base_max_trades + 1, max_trades + 1)
        
        return max_trades
    
    def can_open_new_position(
        self,
        account: AccountState,
        max_concurrent: int
    ) -> Tuple[bool, str]:
        """
        Check if new position can be opened based on current limits.
        """
        if account.open_positions_count >= max_concurrent:
            return False, f"Max concurrent trades reached ({max_concurrent})"
        
        # Check if account has sufficient balance
        if account.balance < 10:  # Minimum $10 balance
            return False, "Insufficient balance"
        
        # Check daily loss limit
        if account.daily_pnl < -10:  # 10% daily loss limit
            return False, "Daily loss limit reached"
        
        return True, "OK"
    
    def validate_parameters(
        self,
        position_size: float,
        leverage: int,
        sl_price: float,
        entry_price: float
    ) -> Tuple[bool, str]:
        """
        Validate calculated parameters before execution.
        
        CRITICAL: Prevents invalid orders due to NaN or extreme values.
        """
        # Check for NaN or infinite values
        if not np.isfinite(position_size) or position_size <= 0:
            return False, f"Invalid position size: {position_size}"
        
        if not np.isfinite(sl_price) or sl_price <= 0:
            return False, f"Invalid SL price: {sl_price}"
        
        if leverage < 1 or leverage > self.max_leverage:
            return False, f"Invalid leverage: {leverage}"
        
        # Check SL distance
        sl_distance = abs(entry_price - sl_price) / entry_price
        if sl_distance < 0.001:  # Less than 0.1%
            return False, f"SL too tight: {sl_distance*100:.3f}%"
        
        if sl_distance > 0.2:  # More than 20%
            return False, f"SL too wide: {sl_distance*100:.3f}%"
        
        return True, "Valid"
