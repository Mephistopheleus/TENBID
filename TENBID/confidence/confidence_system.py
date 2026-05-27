"""
Confidence System v2.0 - Расчет уверенности с полной маркировкой данных
Интегрирован с DataLineageManager для отслеживания происхождения каждой оценки
"""

from typing import Dict, List, Optional, Any
from core.data_lineage import LineageNode, DataLineageManager


class ConfidenceSystem:
    """Система расчета уверенности на основе графа данных"""
    
    def __init__(self, lineage_manager: DataLineageManager = None):
        self.lineage_manager = lineage_manager
        self.weights: Dict[str, float] = {
            'price_action': 0.35,
            'volume': 0.25,
            'sentiment': 0.20,
            'multi_tf': 0.20
        }
    
    def _create_lineage_node(self, operation: str, parents: List[LineageNode] = None, 
                             metadata: Dict = None) -> LineageNode:
        """Создает узел и регистрирует его в менеджере"""
        node = LineageNode(
            operation=operation,
            parents=parents or [],
            metadata=metadata or {}
        )
        if self.lineage_manager:
            self.lineage_manager.add_node(node)
        return node
    
    def _merge_lineages(self, nodes: List[LineageNode], operation: str, 
                        metadata: Dict = None) -> LineageNode:
        """Создает новый узел-ребенок с несколькими родителями"""
        node = LineageNode(
            operation=operation,
            parents=nodes,
            metadata=metadata or {'merged_count': len(nodes)}
        )
        if self.lineage_manager:
            self.lineage_manager.add_node(node)
        return node
    
    def calculate_confidence(self, factors: Dict[str, Any], 
                            lineage_nodes: List[LineageNode] = None) -> tuple:
        """
        Рассчитывает уверенность и создает узел маркировки
        
        Returns:
            tuple: (confidence_score, lineage_node)
        """
        total_confidence = 0.0
        total_weight = 0.0
        
        for factor_name, factor_data in factors.items():
            if factor_name in self.weights:
                weight = self.weights[factor_name]
                # Извлекаем уверенность из данных фактора
                if isinstance(factor_data, dict):
                    factor_conf = factor_data.get('confidence', 0.0)
                elif isinstance(factor_data, (int, float)):
                    factor_conf = float(factor_data)
                else:
                    factor_conf = 0.0
                
                total_confidence += factor_conf * weight
                total_weight += weight
        
        confidence = total_confidence / total_weight if total_weight > 0 else 0.0
        
        # Создаем узел маркировки для этого расчета
        metadata = {
            'factors': list(factors.keys()),
            'weights_used': {k: v for k, v in self.weights.items() if k in factors},
            'raw_confidence': total_confidence,
            'total_weight': total_weight,
            'source_type': 'calculated',
            'quality': 'high' if confidence > 0.7 else 'medium' if confidence > 0.4 else 'low'
        }
        
        lineage_node = self._create_lineage_node(
            operation='confidence_calculation',
            parents=lineage_nodes or [],
            metadata=metadata
        )
        
        return confidence, lineage_node
    
    def merge_signals(self, signals: List[Dict], 
                     lineage_nodes: List[LineageNode]) -> tuple:
        """
        Объединяет несколько сигналов в один с расчетом общей уверенности
        
        Returns:
            tuple: (merged_signal_dict, merged_lineage_node)
        """
        if not signals:
            metadata = {'status': 'empty', 'source_type': 'calculated'}
            node = self._create_lineage_node('signal_merge', parents=[], metadata=metadata)
            return {'confidence': 0.0, 'direction': 'neutral', 'strength': 0.0}, node
        
        # Усредняем направления и взвешиваем уверенность
        total_confidence = sum(s.get('confidence', 0.0) for s in signals)
        avg_confidence = total_confidence / len(signals)
        
        # Определяем доминирующее направление
        bullish = sum(1 for s in signals if s.get('direction') == 'bullish')
        bearish = sum(1 for s in signals if s.get('direction') == 'bearish')
        
        if bullish > bearish:
            direction = 'bullish'
        elif bearish > bullish:
            direction = 'bearish'
        else:
            direction = 'neutral'
        
        strength = abs(bullish - bearish) / len(signals) if signals else 0.0
        
        merged_signal = {
            'confidence': avg_confidence,
            'direction': direction,
            'strength': strength,
            'signals_count': len(signals),
            'bullish_count': bullish,
            'bearish_count': bearish
        }
        
        # Создаем узел слияния со всеми родительскими узлами
        metadata = {
            'operation': 'multi_signal_merge',
            'source_type': 'calculated',
            'quality': 'high' if avg_confidence > 0.7 else 'medium',
            'merged_count': len(signals)
        }
        
        merged_lineage = self._merge_lineages(
            nodes=lineage_nodes,
            operation='signal_merge',
            metadata=metadata
        )
        
        return merged_signal, merged_lineage
    
    def adjust_for_news(self, base_confidence: float, sentiment_score: float,
                       base_lineage: LineageNode) -> tuple:
        """
        Корректирует уверенность на основе новостного сентимента
        
        Returns:
            tuple: (adjusted_confidence, new_lineage_node)
        """
        # Сила влияния новостей (максимум ±30%)
        news_impact = sentiment_score * 0.3
        adjusted = max(0.0, min(1.0, base_confidence + news_impact))
        
        metadata = {
            'base_confidence': base_confidence,
            'sentiment_score': sentiment_score,
            'news_impact': news_impact,
            'adjusted_confidence': adjusted,
            'source_type': 'calculated',
            'quality': 'high'
        }
        
        new_lineage = self._create_lineage_node(
            operation='news_adjustment',
            parents=[base_lineage] if base_lineage else [],
            metadata=metadata
        )
        
        return adjusted, new_lineage
    
    def get_weights(self) -> Dict[str, float]:
        """Возвращает текущие веса факторов"""
        return self.weights.copy()
    
    def update_weights(self, new_weights: Dict[str, float]):
        """Обновляет веса факторов (для автотюнера)"""
        for key, value in new_weights.items():
            if key in self.weights:
                self.weights[key] = value
        
        # Нормализуем веса до суммы 1.0
        total = sum(self.weights.values())
        if total > 0:
            for key in self.weights:
                self.weights[key] /= total
