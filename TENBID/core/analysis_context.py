"""
Analysis Context - единый контейнер для всех данных анализа с маркировкой
Используется для передачи данных между анализаторами и отслеживания происхождения данных
"""

import pandas as pd
from typing import Dict, List, Optional, Any
from core.data_lineage import DataLineageManager, LineageNode, lineage_manager
from datetime import datetime


class AnalysisContext:
    """Контекст анализа - хранит все данные и результаты с полной маркировкой"""
    
    def __init__(self, symbol: str, timeframe: str, snapshot_id: str = None):
        self.symbol = symbol
        self.timeframe = timeframe
        self.snapshot_id = snapshot_id  # ID корневого snapshot узла
        self.market_data: Dict[str, pd.DataFrame] = {}  # {symbol: df}
        self.synthetic_data: Dict[str, pd.DataFrame] = {}  # {timeframe: df}
        self.results: Dict[str, Dict] = {}  # {analyzer_name: result_dict}
        self.node_ids: Dict[str, str] = {}  # {analyzer_name: node_id} - храним ID узлов вместо объектов
        self.metadata: Dict[str, Any] = {
            'created_at': datetime.now().isoformat(),
            'symbol': symbol,
            'timeframe': timeframe
        }
    
    def add_market_data(self, symbol: str, df: pd.DataFrame):
        """Добавляет рыночные данные (свечи)"""
        self.market_data[symbol] = df
    
    def add_synthetic_data(self, timeframe: str, df: pd.DataFrame):
        """Добавляет синтетические таймфреймы"""
        self.synthetic_data[timeframe] = df
    
    def get_data(self, source_type: str, symbol: str = None, timeframe: str = None) -> Optional[pd.DataFrame]:
        """Получает данные по типу источника
        
        Args:
            source_type: 'MARKET_DATA' или 'SYNTHETIC_TF'
            symbol: для MARKET_DATA
            timeframe: для SYNTHETIC_TF
        """
        if source_type == 'MARKET_DATA':
            return self.market_data.get(symbol) if symbol else next(iter(self.market_data.values()), None)
        elif source_type == 'SYNTHETIC_TF':
            return self.synthetic_data.get(timeframe) if timeframe else next(iter(self.synthetic_data.values()), None)
        return None
    
    def add_result(self, analyzer_name: str, result: Dict, node_id: str = None):
        """Добавляет результат анализа с маркировкой
        
        Args:
            analyzer_name: имя анализатора
            result: словарь результатов
            node_id: ID узла в графе lineage (вместо старого объекта DataLineage)
        """
        self.results[analyzer_name] = result
        if node_id:
            self.node_ids[analyzer_name] = node_id
    
    def get_result(self, analyzer_name: str) -> Optional[Dict]:
        """Получает результат анализа по имени"""
        return self.results.get(analyzer_name)
    
    def get_all_results(self) -> Dict[str, Dict]:
        """Возвращает все результаты анализа"""
        return self.results.copy()
    
    def get_confidence_weighted(self) -> float:
        """Вычисляет средневзвешенную уверенность всех результатов"""
        if not self.results:
            return 0.0
        
        total_confidence = 0.0
        count = 0
        for result in self.results.values():
            if 'confidence' in result:
                total_confidence += result['confidence']
                count += 1
        
        return total_confidence / count if count > 0 else 0.0
    
    def get_node_chain(self, analyzer_name: str = None) -> List[str]:
        """Возвращает цепочку ID узлов для трассировки
        
        Args:
            analyzer_name: если указан, возвращает ID конкретного узла
        """
        if analyzer_name:
            node_id = self.node_ids.get(analyzer_name)
            return [node_id] if node_id else []
        
        return list(self.node_ids.values())
    
    def summarize(self) -> Dict:
        """Краткая сводка контекста для логирования"""
        return {
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'snapshot_id': self.snapshot_id,
            'market_data_symbols': list(self.market_data.keys()),
            'synthetic_timeframes': list(self.synthetic_data.keys()),
            'analyzers_run': list(self.results.keys()),
            'avg_confidence': self.get_confidence_weighted(),
            'has_lineage': len(self.node_ids) > 0
        }
