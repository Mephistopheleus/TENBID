"""Confidence System - calculates trade confidence with adaptive weights and lineage tracking v2.0"""
import logging
from typing import Dict, List, Optional, Any
from core.data_lineage import DataLineageManager

logger = logging.getLogger(__name__)

class ConfidenceSystem:
    def __init__(self, config, lineage_manager: DataLineageManager, initial_weights=None):
        self.lineage_manager = lineage_manager
        self.base_threshold = config.getfloat('CONFIDENCE', 'base_confidence_threshold')
        self.adaptive_enabled = config.getboolean('CONFIDENCE', 'adaptive_threshold_enabled')
        self.min_threshold = config.getfloat('CONFIDENCE', 'min_threshold')
        self.max_threshold = config.getfloat('CONFIDENCE', 'max_threshold')
        self.volatility_factor = config.getfloat('CONFIDENCE', 'volatility_impact_factor')
        
        # Weights are now EXCLUSIVELY provided by Autotuner - no hardcoded defaults
        # If no weights provided, use neutral weights (all 1.0) as temporary fallback
        if initial_weights:
            self.weights = initial_weights
        else:
            # Neutral fallback - should be replaced by autotuner on first optimization cycle
            self.weights = {
                'trend': 1.0,
                'support_resistance': 1.0,
                'volume': 1.0,
                'pattern': 1.0,
                'orderbook': 1.0,
                'correlation': 1.0,
                'fractal': 1.0,
                'regime': 1.0
            }
    
    def calculate(self, snapshot_id: str, analysis: Dict, data_dict: Dict, 
                  btc_result: Optional[Dict] = None, fractal_result: Optional[Dict] = None, 
                  orderbook_result: Optional[Dict] = None, pattern_result: Optional[Dict] = None, 
                  regime_result: Optional[Dict] = None, override_weights: Optional[Dict] = None,
                  context_profile_id: Optional[str] = None):
        """Calculate total confidence score from analysis with full lineage tracking v2.0
        
        Args:
            snapshot_id: ID корневого снимка рынка (от DataLineageManager)
            analysis: dict {timeframe: analysis_dict} с данными индикаторов
            data_dict: dict {timeframe: (df, metadata)} исходные данные
            btc_result: результат анализа BTC корреляции
            fractal_result: результат фрактального анализа
            orderbook_result: результат анализа стакана
            pattern_result: результат анализа паттернов
            regime_result: результат определения рыночного режима
            override_weights: REQUIRED - weights from Autotuner
            context_profile_id: ID профиля контекста (опционально)
            
        Returns:
            dict: {
                'confidence': float,
                'matrix_node_id': str,
                'breakdown': dict,
                'recommendation': str
            }
        """
        # CRITICAL: Must receive weights from Autotuner - no hardcoded values
        if override_weights is None:
            logger.warning("No override_weights provided to calculate(). Using internal weights (should come from Autotuner).")
        
        weights = override_weights if override_weights else self.weights.copy()
        
        scores: Dict[str, float] = {}
        analysis_ids: List[str] = []
        breakdown: Dict[str, Any] = {}
        
        # --- 1. Trend Score (multi-timeframe agreement) ---
        trend_scores = []
        trend_details = {}
        for tf, data in analysis.items():
            if 'trend' in data:
                trend_scores.append(data['trend'])
                trend_details[tf] = data['trend']
        
        if trend_scores:
            avg_trend = sum(trend_scores) / len(trend_scores)
            scores['trend'] = (avg_trend + 1) / 2  # Normalize to 0-1
            trend_direction = 'BULLISH' if avg_trend > 0.2 else ('BEARISH' if avg_trend < -0.2 else 'NEUTRAL')
        else:
            scores['trend'] = 0.5
            trend_direction = 'NEUTRAL'
        
        # Создаем узел анализа для тренда
        try:
            trend_node_id = self.lineage_manager.create_analysis_node(
                parent_snapshot_id=snapshot_id,
                analyzer_name="confidence_component_trend",
                result_vector={'scores': trend_details, 'average': avg_trend if trend_scores else None, 'direction': trend_direction},
                confidence=scores['trend'],
                additional_metadata={'component': 'trend', 'normalization': '(avg+1)/2'}
            )
            analysis_ids.append(trend_node_id)
        except Exception as e:
            logger.error(f"Failed to create trend analysis node: {e}")
        
        # --- 2. Support/Resistance Score ---
        sr_scores = []
        sr_details = {}
        for tf, data in analysis.items():
            if 'sr_strength' in data:
                val = data.get('sr_strength', 0.5)
                sr_scores.append(val)
                sr_details[tf] = val
        
        if sr_scores:
            scores['support_resistance'] = max(sr_scores)
        else:
            scores['support_resistance'] = 0.5
        
        try:
            sr_node_id = self.lineage_manager.create_analysis_node(
                parent_snapshot_id=snapshot_id,
                analyzer_name="confidence_component_sr",
                result_vector={'scores': sr_details, 'max_score': scores['support_resistance']},
                confidence=scores['support_resistance'],
                additional_metadata={'component': 'support_resistance', 'method': 'max_strength'}
            )
            analysis_ids.append(sr_node_id)
        except Exception as e:
            logger.error(f"Failed to create SR analysis node: {e}")
        
        # --- 3. Volume Score ---
        vol_scores = []
        vol_details = {}
        for tf, data in analysis.items():
            if 'volume_score' in data:
                val = data.get('volume_score', 0.5)
                vol_scores.append(val)
                vol_details[tf] = val
        
        if vol_scores:
            scores['volume'] = sum(vol_scores) / len(vol_scores)
        else:
            scores['volume'] = 0.5
        
        try:
            vol_node_id = self.lineage_manager.create_analysis_node(
                parent_snapshot_id=snapshot_id,
                analyzer_name="confidence_component_volume",
                result_vector={'scores': vol_details, 'average': scores['volume']},
                confidence=scores['volume'],
                additional_metadata={'component': 'volume', 'method': 'average'}
            )
            analysis_ids.append(vol_node_id)
        except Exception as e:
            logger.error(f"Failed to create volume analysis node: {e}")
        
        # --- 4. Pattern Score ---
        if pattern_result and 'confidence' in pattern_result:
            scores['pattern'] = pattern_result.get('confidence', 0.7)
            pattern_data = pattern_result.get('data', {})
        else:
            scores['pattern'] = 0.7
            pattern_data = {'note': 'default_pattern_score'}
        
        try:
            pattern_node_id = self.lineage_manager.create_analysis_node(
                parent_snapshot_id=snapshot_id,
                analyzer_name="confidence_component_pattern",
                result_vector={'data': pattern_data, 'confidence': scores['pattern']},
                confidence=scores['pattern'],
                additional_metadata={'component': 'pattern', 'source': 'pattern_recognition'}
            )
            analysis_ids.append(pattern_node_id)
        except Exception as e:
            logger.error(f"Failed to create pattern analysis node: {e}")
        
        # --- 5. Orderbook Score ---
        if orderbook_result and 'confidence' in orderbook_result:
            scores['orderbook'] = orderbook_result.get('confidence', 0.6)
            orderbook_data = orderbook_result.get('data', {})
        else:
            scores['orderbook'] = 0.6
            orderbook_data = {'note': 'default_orderbook_score'}
        
        try:
            ob_node_id = self.lineage_manager.create_analysis_node(
                parent_snapshot_id=snapshot_id,
                analyzer_name="confidence_component_orderbook",
                result_vector={'data': orderbook_data, 'confidence': scores['orderbook']},
                confidence=scores['orderbook'],
                additional_metadata={'component': 'orderbook', 'source': 'orderbook_analysis'}
            )
            analysis_ids.append(ob_node_id)
        except Exception as e:
            logger.error(f"Failed to create orderbook analysis node: {e}")
        
        # --- 6. Correlation Score (BTC) ---
        if btc_result and 'confidence' in btc_result:
            scores['correlation'] = btc_result.get('confidence', 0.5)
            corr_data = btc_result.get('data', {})
        else:
            scores['correlation'] = 0.5
            corr_data = {'note': 'default_correlation_score'}
        
        try:
            corr_node_id = self.lineage_manager.create_analysis_node(
                parent_snapshot_id=snapshot_id,
                analyzer_name="confidence_component_correlation",
                result_vector={'data': corr_data, 'confidence': scores['correlation']},
                confidence=scores['correlation'],
                additional_metadata={'component': 'correlation', 'source': 'btc_correlation'}
            )
            analysis_ids.append(corr_node_id)
        except Exception as e:
            logger.error(f"Failed to create correlation analysis node: {e}")
        
        # --- 7. Fractal Score ---
        if fractal_result and 'confidence' in fractal_result:
            scores['fractal'] = fractal_result.get('confidence', 0.5)
            fractal_data = fractal_result.get('data', {})
        else:
            scores['fractal'] = 0.5
            fractal_data = {'note': 'default_fractal_score'}
        
        try:
            fractal_node_id = self.lineage_manager.create_analysis_node(
                parent_snapshot_id=snapshot_id,
                analyzer_name="confidence_component_fractal",
                result_vector={'data': fractal_data, 'confidence': scores['fractal']},
                confidence=scores['fractal'],
                additional_metadata={'component': 'fractal', 'source': 'fractal_analysis'}
            )
            analysis_ids.append(fractal_node_id)
        except Exception as e:
            logger.error(f"Failed to create fractal analysis node: {e}")
        
        # --- 8. Regime Score ---
        regime = 'UNKNOWN'
        if regime_result and 'confidence' in regime_result:
            regime = regime_result.get('regime', 'UNKNOWN')
            base_confidence = regime_result.get('confidence', 0.5)
            regime_data = regime_result.get('data', {})
            
            # Адаптируем оценку в зависимости от режима
            if regime == 'HIGH_VOLATILITY':
                scores['regime'] = base_confidence * 0.7  # Штраф за хаос
            elif regime == 'RANGING':
                scores['regime'] = base_confidence * 0.85  # Штраф за флэт
            elif regime in ['TREND_UP', 'TREND_DOWN']:
                scores['regime'] = base_confidence  # Без штрафа
            else:
                scores['regime'] = 0.5
        else:
            scores['regime'] = 0.5
            regime_data = {'note': 'default_regime_score'}
        
        try:
            regime_node_id = self.lineage_manager.create_analysis_node(
                parent_snapshot_id=snapshot_id,
                analyzer_name="confidence_component_regime",
                result_vector={'regime': regime, 'data': regime_data, 'base_confidence': regime_result.get('confidence', 0.5) if regime_result else 0.5, 'adjusted_confidence': scores['regime']},
                confidence=scores['regime'],
                additional_metadata={'component': 'regime', 'source': 'market_regime'}
            )
            analysis_ids.append(regime_node_id)
        except Exception as e:
            logger.error(f"Failed to create regime analysis node: {e}")
        
        # --- Calculate Weighted Average ---
        total_weight = sum(weights.values())
        if total_weight == 0:
            logger.warning("Total weight is zero, using equal weights")
            total_weight = len(scores)
            for k in scores:
                weights[k] = 1.0
        
        weighted_sum = sum(scores[k] * weights.get(k, 1.0) for k in scores)
        total_confidence = weighted_sum / total_weight
        
        # --- Determine Recommendation ---
        # Логика: если уверенность выше порога и тренд положительный -> BUY, отрицательный -> SELL
        current_threshold = self.get_adaptive_threshold(analysis)
        
        if total_confidence >= current_threshold:
            if trend_direction == 'BULLISH':
                recommendation = 'BUY'
            elif trend_direction == 'BEARISH':
                recommendation = 'SELL'
            else:
                # Если тренд нейтральный, но уверенность высокая - можно воздержаться или следовать мелким сигналам
                # Для безопасности лучше HOLD, если нет явного направления
                recommendation = 'HOLD'
        else:
            recommendation = 'HOLD'
        
        # Формируем breakdown для вероятностного поля
        breakdown = {
            'component_scores': scores,
            'weights_used': weights.copy(),
            'total_weight': total_weight,
            'weighted_sum': weighted_sum,
            'threshold_used': current_threshold,
            'trend_direction': trend_direction,
            'regime': regime
        }
        
        final_vector = {
            'confidence': total_confidence,
            'action': recommendation,
            'regime': regime,
            'trend': trend_direction
        }
        
        # --- Create Matrix Decision Node ---
        matrix_node_id = ""
        if analysis_ids:
            try:
                matrix_node_id = self.lineage_manager.create_matrix_decision_node(
                    input_analysis_ids=analysis_ids,
                    probability_field=breakdown,
                    final_vector=final_vector,
                    context_profile_id=context_profile_id
                )
            except Exception as e:
                logger.error(f"Failed to create matrix decision node: {e}")
                # Fallback: создаем узел без родителей, если что-то пошло не так (не должно случаться)
                try:
                    # Пытаемся создать хотя бы узел решения, помечая ошибку
                    matrix_node_id = self.lineage_manager.create_matrix_decision_node(
                        input_analysis_ids=[], # Пусто, будет ошибка внутри, но попробуем обработать
                        probability_field={'error': str(e), 'fallback': True},
                        final_vector=final_vector,
                        context_profile_id=context_profile_id
                    )
                except:
                    pass # Если совсем не вышло, оставляем пустым
        else:
            logger.warning("No analysis nodes created, skipping matrix decision node creation")
        
        return {
            'confidence': total_confidence,
            'matrix_node_id': matrix_node_id,
            'breakdown': breakdown,
            'recommendation': recommendation
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

