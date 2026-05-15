"""Confidence System - calculates trade confidence with adaptive weights and lineage tracking"""
from core.data_lineage import LineageTracker, DataSource, DataQuality, DataLineage

class ConfidenceSystem:
    def __init__(self, config, initial_weights=None):
        self.base_threshold = config.getfloat('CONFIDENCE', 'base_confidence_threshold')
        self.adaptive_enabled = config.getboolean('CONFIDENCE', 'adaptive_threshold_enabled')
        self.min_threshold = config.getfloat('CONFIDENCE', 'min_threshold')
        self.max_threshold = config.getfloat('CONFIDENCE', 'max_threshold')
        self.volatility_factor = config.getfloat('CONFIDENCE', 'volatility_impact_factor')
        
        # Component weights (will be tuned by autotuner)
        if initial_weights:
            self.weights = initial_weights
        else:
            self.weights = {
                'trend': 1.0,
                'support_resistance': 1.2,
                'volume': 0.8,
                'pattern': 0.9,
                'orderbook': 1.5,
                'correlation': 1.1,
                'fractal': 1.3,
                'regime': 2.0
            }
    
    def calculate(self, analysis, data_dict, btc_result=None, fractal_result=None, orderbook_result=None, pattern_result=None, regime_result=None, override_weights=None):
        """Calculate total confidence score from analysis with lineage
        
        Args:
            analysis: dict {timeframe: analysis_dict} с маркировкой в 'lineage'
            data_dict: dict {timeframe: (df, lineage)} исходные данные
            btc_result: результат анализа BTC корреляции
            fractal_result: результат фрактального анализа
            orderbook_result: результат анализа стакана
            pattern_result: результат анализа паттернов
            regime_result: результат определения рыночного режима
            override_weights: опциональные веса от Autotuner
            
        Returns:
            dict: {
                'total_confidence': float,
                'component_scores': dict,
                'weights_used': dict,
                'score_lineage': DataLineage,
                'component_lineages': dict
            }
        """
        # Use override weights from Autotuner if provided
        weights = override_weights if override_weights else self.weights.copy()
        
        scores = {}
        component_lineages = {}
        all_lineages = []
        
        # Trend score (multi-timeframe agreement)
        trend_scores = []
        trend_lineages = []
        for tf, data in analysis.items():
            if 'trend' in data:
                trend_scores.append(data['trend'])
                if 'lineage' in data:
                    trend_lineages.append(data['lineage'])
        
        if trend_scores:
            avg_trend = sum(trend_scores) / len(trend_scores)
            scores['trend'] = (avg_trend + 1) / 2  # Normalize to 0-1
            
            # Создаем маркировку для тренд скоринга
            if trend_lineages:
                merged_trend_lineage = LineageTracker.merge_lineages(
                    trend_lineages,
                    method="multi_tf_trend_agreement"
                )
                component_lineages['trend'] = merged_trend_lineage
                all_lineages.append(merged_trend_lineage)
        else:
            scores['trend'] = 0.5
        
        # Support/Resistance score
        sr_scores = []
        sr_lineages = []
        for tf, data in analysis.items():
            if 'sr_strength' in data:
                sr_scores.append(data.get('sr_strength', 0.5))
                if 'lineage' in data:
                    sr_lineages.append(data['lineage'])
        
        if sr_scores:
            scores['support_resistance'] = max(sr_scores)
            if sr_lineages:
                merged_sr_lineage = LineageTracker.merge_lineages(
                    sr_lineages,
                    method="max_sr_strength"
                )
                component_lineages['support_resistance'] = merged_sr_lineage
                all_lineages.append(merged_sr_lineage)
        else:
            scores['support_resistance'] = 0.5
        
        # Volume score
        vol_scores = []
        vol_lineages = []
        for tf, data in analysis.items():
            if 'volume_score' in data:
                vol_scores.append(data.get('volume_score', 0.5))
                if 'lineage' in data:
                    vol_lineages.append(data['lineage'])
        
        if vol_scores:
            scores['volume'] = sum(vol_scores) / len(vol_scores)
            if vol_lineages:
                merged_vol_lineage = LineageTracker.merge_lineages(
                    vol_lineages,
                    method="average_volume_score"
                )
                component_lineages['volume'] = merged_vol_lineage
                all_lineages.append(merged_vol_lineage)
        else:
            scores['volume'] = 0.5
        
        # Pattern score - из реального анализа паттернов
        if pattern_result and 'confidence' in pattern_result:
            scores['pattern'] = pattern_result.get('confidence', 0.7)
            if 'lineage' in pattern_result and pattern_result['lineage']:
                component_lineages['pattern'] = pattern_result['lineage']
                all_lineages.append(pattern_result['lineage'])
        else:
            scores['pattern'] = 0.7
            pattern_lineage = LineageTracker.create_from_source(
                source=DataSource.CALCULATED,
                quality=DataQuality.LOW,
                metadata={'note': 'default_pattern_score'}
            )
            component_lineages['pattern'] = pattern_lineage
            all_lineages.append(pattern_lineage)
        
        # Orderbook score - из реального анализа стакана
        if orderbook_result and 'confidence' in orderbook_result:
            scores['orderbook'] = orderbook_result.get('confidence', 0.6)
            if 'lineage' in orderbook_result and orderbook_result['lineage']:
                component_lineages['orderbook'] = orderbook_result['lineage']
                all_lineages.append(orderbook_result['lineage'])
        else:
            scores['orderbook'] = 0.6
            orderbook_lineage = LineageTracker.create_from_source(
                source=DataSource.CALCULATED,
                quality=DataQuality.LOW,
                metadata={'note': 'default_orderbook_score'}
            )
            component_lineages['orderbook'] = orderbook_lineage
            all_lineages.append(orderbook_lineage)
        
        # Correlation score - из реального анализа BTC
        if btc_result and 'confidence' in btc_result:
            scores['correlation'] = btc_result.get('confidence', 0.5)
            if 'lineage' in btc_result and btc_result['lineage']:
                component_lineages['correlation'] = btc_result['lineage']
                all_lineages.append(btc_result['lineage'])
        else:
            scores['correlation'] = 0.5
            correlation_lineage = LineageTracker.create_from_source(
                source=DataSource.CALCULATED,
                quality=DataQuality.LOW,
                metadata={'note': 'default_correlation_score'}
            )
            component_lineages['correlation'] = correlation_lineage
            all_lineages.append(correlation_lineage)
        
        # Fractal score - из фрактального анализа (добавляем как новый компонент)
        if fractal_result and 'confidence' in fractal_result:
            scores['fractal'] = fractal_result.get('confidence', 0.5)
            self.weights['fractal'] = 1.3  # Добавляем вес для фракталов
            if 'lineage' in fractal_result and fractal_result['lineage']:
                component_lineages['fractal'] = fractal_result['lineage']
                all_lineages.append(fractal_result['lineage'])
        else:
            scores['fractal'] = 0.5
            self.weights['fractal'] = 1.3
            fractal_lineage = LineageTracker.create_from_source(
                source=DataSource.CALCULATED,
                quality=DataQuality.LOW,
                metadata={'note': 'default_fractal_score'}
            )
            component_lineages['fractal'] = fractal_lineage
            all_lineages.append(fractal_lineage)
        
        # Regime score - из определения рыночного режима (критически важный фильтр)
        if regime_result and 'confidence' in regime_result:
            regime = regime_result.get('regime', 'UNKNOWN')
            base_confidence = regime_result.get('confidence', 0.5)
            
            # Адаптируем вес в зависимости от режима
            # В режиме HIGH_VOLATILITY снижаем доверие ко всем сигналам
            if regime == 'HIGH_VOLATILITY':
                scores['regime'] = base_confidence * 0.7  # Штраф за хаос
                self.weights['regime'] = 2.0  # Высокий вес - режим очень важен
            elif regime == 'RANGING':
                # Во флэте трендовые стратегии работают хуже
                scores['regime'] = base_confidence * 0.85
                self.weights['regime'] = 1.8
            elif regime in ['TREND_UP', 'TREND_DOWN']:
                # В тренде повышаем доверие
                scores['regime'] = base_confidence
                self.weights['regime'] = 2.5  # Максимальный вес для тренда
            else:
                scores['regime'] = 0.5
                self.weights['regime'] = 1.5
            
            if 'lineage' in regime_result and regime_result['lineage']:
                component_lineages['regime'] = regime_result['lineage']
                all_lineages.append(regime_result['lineage'])
        else:
            scores['regime'] = 0.5
            self.weights['regime'] = 1.5
            regime_lineage = LineageTracker.create_from_source(
                source=DataSource.CALCULATED,
                quality=DataQuality.LOW,
                metadata={'note': 'default_regime_score'}
            )
            component_lineages['regime'] = regime_lineage
            all_lineages.append(regime_lineage)
        
        # Calculate weighted average
        total_weight = sum(weights.values())
        weighted_sum = sum(scores[k] * weights.get(k, 1.0) for k in scores)
        total_confidence = weighted_sum / total_weight
        
        # Создаем итоговую маркировку для общего confidence
        if all_lineages:
            score_lineage = LineageTracker.merge_lineages(
                all_lineages,
                method="weighted_confidence_calculation"
            )
        else:
            score_lineage = None
        
        return {
            'total_confidence': total_confidence,
            'component_scores': scores,
            'weights_used': weights.copy(),
            'score_lineage': score_lineage,
            'component_lineages': component_lineages
        }
    
    def get_adaptive_threshold(self, analysis):
        """Calculate adaptive threshold based on market conditions"""
        if not self.adaptive_enabled:
            return self.base_threshold
        
        # Calculate average volatility (ATR normalized)
        atr_values = [v.get('atr', 0) for v in analysis.values() if 'atr' in v]
        avg_atr = sum(atr_values) / len(atr_values) if atr_values else 0
        
        # Get current price for normalization
        prices = [v.get('price', 1) for v in analysis.values() if 'price' in v]
        avg_price = sum(prices) / len(prices) if prices else 1
        
        # Normalized volatility
        norm_vol = avg_atr / avg_price if avg_price > 0 else 0
        
        # Adjust threshold: higher vol -> higher threshold
        adjustment = norm_vol * self.volatility_factor * 100
        adaptive_threshold = self.base_threshold + adjustment
        
        # Clamp to min/max
        return max(self.min_threshold, min(self.max_threshold, adaptive_threshold))

