"""
TENBID - Mathematical Analysis Module
Technical indicators and statistical analysis for scalping
"""

import numpy as np
from typing import List, Dict, Tuple
from collections import deque

class MathAnalyzer:
    def __init__(self, window_size: int = 20):
        self.window_size = window_size
        self.price_history = deque(maxlen=1000)
        self.volume_history = deque(maxlen=1000)
        
    def add_data_point(self, price: float, volume: float, timestamp: int):
        """Add new price/volume data point"""
        self.price_history.append((timestamp, price, volume))
        self.volume_history.append((timestamp, volume))
    
    def get_prices(self) -> np.ndarray:
        """Get array of prices"""
        if len(self.price_history) == 0:
            return np.array([])
        return np.array([p[1] for p in self.price_history])
    
    def calculate_sma(self, period: int = 20) -> Optional[float]:
        """Simple Moving Average"""
        prices = self.get_prices()
        if len(prices) < period:
            return None
        return float(np.mean(prices[-period:]))
    
    def calculate_ema(self, period: int = 20) -> Optional[float]:
        """Exponential Moving Average"""
        prices = self.get_prices()
        if len(prices) < period:
            return None
        
        multiplier = 2 / (period + 1)
        ema = prices[0]
        for price in prices[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        return float(ema)
    
    def calculate_rsi(self, period: int = 14) -> Optional[float]:
        """Relative Strength Index"""
        prices = self.get_prices()
        if len(prices) < period + 1:
            return None
        
        deltas = np.diff(prices[-period-1:])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi)
    
    def calculate_bollinger_bands(self, period: int = 20, std_dev: float = 2.0) -> Optional[Tuple[float, float, float]]:
        """Bollinger Bands: (lower, middle, upper)"""
        prices = self.get_prices()
        if len(prices) < period:
            return None
        
        middle = np.mean(prices[-period:])
        std = np.std(prices[-period:])
        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)
        
        return (float(lower), float(middle), float(upper))
    
    def calculate_atr(self, period: int = 14) -> Optional[float]:
        """Average True Range - volatility measure"""
        prices = self.get_prices()
        if len(prices) < period + 1:
            return None
        
        true_ranges = []
        for i in range(1, len(prices)):
            high = prices[i]
            low = prices[i]
            prev_close = prices[i-1]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)
        
        return float(np.mean(true_ranges[-period:]))
    
    def calculate_macd(self, fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[Tuple[float, float, float]]:
        """MACD: (macd_line, signal_line, histogram)"""
        prices = self.get_prices()
        if len(prices) < slow:
            return None
        
        # Calculate EMAs
        def calc_ema(data, period):
            multiplier = 2 / (period + 1)
            ema = data[0]
            for value in data[1:]:
                ema = (value * multiplier) + (ema * (1 - multiplier))
            return ema
        
        # This is simplified - full implementation would calculate EMA for each point
        fast_ema = calc_ema(prices[-fast:], fast)
        slow_ema = calc_ema(prices[-slow:], slow)
        
        macd_line = fast_ema - slow_ema
        # Signal line calculation simplified
        signal_line = macd_line * 0.8  # Simplified
        histogram = macd_line - signal_line
        
        return (float(macd_line), float(signal_line), float(histogram))
    
    def calculate_vwap(self) -> Optional[float]:
        """Volume Weighted Average Price"""
        if len(self.price_history) == 0:
            return None
        
        total_volume = 0
        total_pv = 0
        
        for timestamp, price, volume in self.price_history:
            total_pv += price * volume
            total_volume += volume
        
        if total_volume == 0:
            return None
        
        return float(total_pv / total_volume)
    
    def detect_trend(self, short_period: int = 5, long_period: int = 20) -> str:
        """Detect current trend: 'uptrend', 'downtrend', or 'sideways'"""
        prices = self.get_prices()
        if len(prices) < long_period:
            return "unknown"
        
        short_sma = np.mean(prices[-short_period:])
        long_sma = np.mean(prices[-long_period:])
        
        threshold = 0.001  # 0.1% threshold
        
        if short_sma > long_sma * (1 + threshold):
            return "uptrend"
        elif short_sma < long_sma * (1 - threshold):
            return "downtrend"
        else:
            return "sideways"
    
    def calculate_volatility(self, period: int = 20) -> Optional[float]:
        """Calculate price volatility (standard deviation of returns)"""
        prices = self.get_prices()
        if len(prices) < period + 1:
            return None
        
        returns = np.diff(prices[-period-1:]) / prices[-period-1:-1]
        return float(np.std(returns))
    
    def get_analysis_summary(self) -> Dict:
        """Get comprehensive analysis summary"""
        return {
            "sma_20": self.calculate_sma(20),
            "ema_20": self.calculate_ema(20),
            "rsi_14": self.calculate_rsi(14),
            "bollinger": self.calculate_bollinger_bands(),
            "atr_14": self.calculate_atr(14),
            "macd": self.calculate_macd(),
            "vwap": self.calculate_vwap(),
            "trend": self.detect_trend(),
            "volatility": self.calculate_volatility(),
            "data_points": len(self.price_history)
        }


if __name__ == "__main__":
    # Test with sample data
    analyzer = MathAnalyzer()
    
    import time
    base_price = 50000
    
    print("Testing Math Analyzer with simulated data...")
    for i in range(50):
        price = base_price + np.random.randn() * 100
        volume = np.random.randint(100, 1000)
        analyzer.add_data_point(price, volume, int(time.time()))
        base_price = price
    
    summary = analyzer.get_analysis_summary()
    print("\nAnalysis Summary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")
