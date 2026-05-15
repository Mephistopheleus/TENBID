"""
Analysis Context - единый контейнер для всех данных анализа с маркировкой
Используется для передачи данных между анализаторами и отслеживания происхождения данных
"""

import pandas as pd
from typing import Dict, List, Optional, Any
from core.data_lineage import DataLineage, DataSource, DataQuality, LineageTracker
from datetime import datetime


class AnalysisContext:
    """Контекст анализа - хранит все данные и результаты с полной маркировкой"""
    
    def __init__(self, symbol: str, timeframe: str, base_lineage: DataLineage = None):
        self.symbol = symbol
        self.timeframe = timeframe
        self.data_lineage = base_lineage
        self.market_data: Dict[str, pd.DataFrame] = {}  # {symbol: df}
        self.synthetic_data: Dict[str, pd.DataFrame] = {}  # {timeframe: df}
        self.results: Dict[str, Dict] = {}  # {analyzer_name: result_dict}
        self.lineages: Dict[str, DataLineage] = {}  # {analyzer_name: lineage}
        self.metadata: Dict[str, Any] = {
            'created_at': datetime.now().isoformat(),
            'symbol': symbol,
            'timeframe': timeframe
        }
    
    def add_market_data(self, symbol: str, df: pd.DataFrame, lineage: DataLineage = None):
        """Добавляет рыночные данные (свечи)"""
        self.market_data[symbol] = df
        if lineage:
            self.lineages[f'market_{symbol}'] = lineage
    
    def add_synthetic_data(self, timeframe: str, df: pd.DataFrame, lineage: DataLineage = None):
        """Добавляет синтетические таймфреймы"""
        self.synthetic_data[timeframe] = df
        if lineage:
            self.lineages[f'synthetic_{timeframe}'] = lineage
    
    def get_data(self, source: DataSource, symbol: str = None, timeframe: str = None) -> Optional[pd.DataFrame]:
        """Получает данные по типу источника"""
        if source == DataSource.MARKET_DATA:
            return self.market_data.get(symbol) if symbol else next(iter(self.market_data.values()), None)
        elif source == DataSource.SYNTHETIC_TF:
            return self.synthetic_data.get(timeframe) if timeframe else next(iter(self.synthetic_data.values()), None)
        return None
    
    def add_result(self, analyzer_name: str, result: Dict, lineage: DataLineage = None):
        """Добавляет результат анализа с маркировкой"""
        self.results[analyzer_name] = result
        if lineage:
            self.lineages[analyzer_name] = lineage
    
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
    
    def get_lineage_chain(self, analyzer_name: str = None) -> List[DataLineage]:
        """Возвращает цепочку маркировок для трассировки"""
        if analyzer_name:
            lineage = self.lineages.get(analyzer_name)
            return [lineage] if lineage else []
        
        return list(self.lineages.values())
    
    def summarize(self) -> Dict:
        """Краткая сводка контекста для логирования"""
        return {
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'market_data_symbols': list(self.market_data.keys()),
            'synthetic_timeframes': list(self.synthetic_data.keys()),
            'analyzers_run': list(self.results.keys()),
            'avg_confidence': self.get_confidence_weighted(),
            'has_lineage': len(self.lineages) > 0
        }
