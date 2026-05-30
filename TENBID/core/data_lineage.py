"""
TENBID Data Lineage System v2.0
Сквозная маркировка данных и событий для полного аудита и обучения Автотюнера.

Каждый снимок, анализ, решение и сделка получают уникальный ID и сохраняют связь с предками.
Это позволяет Автотюнеру видеть полную цепочку: "Кто повлиял и как" на каждом шагу.

АРХИТЕКТУРА:
- Каждый снимок данных -> уникальный snap_ID
- Каждый анализ -> analysis_ID с привязкой к snap_ID
- Решение матрицы -> matrix_ID с привязкой ко всем input analysis_ID
- Исполнение -> exec_ID с привязкой к matrix_ID
- Теневик/Лаборатория -> shadow_ID с привязкой к snap_ID или analysis_ID
- Каждый шаг маркируется персонально для разбора "кто повлиял и как"
"""

import uuid
import time
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from enum import Enum
import hashlib
import logging

logger = logging.getLogger(__name__)


class DataSource(Enum):
    """Legacy data source identifiers used by analyzers."""
    BINANCE_API = "binance_api"
    BINANCE_WEBSOCKET = "binance_websocket"
    MARKET_DATA = "market_data"
    SYNTHETIC_TF = "synthetic_timeframe"
    CALCULATED = "calculated"
    EXTERNAL = "external"
    USER_INPUT = "user_input"


class DataQuality(Enum):
    """Legacy data quality levels used by analyzers."""
    HIGH = 1.0
    MEDIUM = 0.7
    LOW = 0.4
    VERY_LOW = 0.2

    @classmethod
    def from_score(cls, score: float) -> 'DataQuality':
        if score >= cls.HIGH.value:
            return cls.HIGH
        if score >= cls.MEDIUM.value:
            return cls.MEDIUM
        if score >= cls.LOW.value:
            return cls.LOW
        return cls.VERY_LOW


@dataclass
class DataLineage:
    """Compatibility lineage object for older analyzer code."""
    source: DataSource
    quality: DataQuality
    timestamp: datetime
    age_seconds: float = 0.0
    dependencies: List['DataLineage'] = field(default_factory=list)
    calculation_method: Optional[str] = None
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.age_seconds == 0.0:
            self.age_seconds = (datetime.now() - self.timestamp).total_seconds()
        time_decay = max(0.0, 1.0 - (self.age_seconds / 3600))
        self.confidence = self.quality.value * time_decay

    def to_dict(self) -> Dict[str, Any]:
        return {
            'source': self.source.value,
            'quality': self.quality.value,
            'timestamp': self.timestamp.isoformat(),
            'age_seconds': self.age_seconds,
            'calculation_method': self.calculation_method,
            'confidence': self.confidence,
            'metadata': self.metadata,
            'dependencies_count': len(self.dependencies),
        }

    def get_lineage_tree(self, depth: int = 0) -> str:
        indent = "  " * depth
        result = f"{indent}├─ {self.source.value} (q={self.quality.value:.2f}, c={self.confidence:.2f})"
        if self.calculation_method:
            result += f" [{self.calculation_method}]"
        result += "\n"
        for dependency in self.dependencies:
            result += dependency.get_lineage_tree(depth + 1)
        return result


class LineageTracker:
    """Compatibility helper for older analyzer code."""

    @staticmethod
    def create_from_source(
        source: DataSource,
        quality: DataQuality,
        metadata: Optional[Dict] = None,
    ) -> DataLineage:
        return DataLineage(
            source=source,
            quality=quality,
            timestamp=datetime.now(),
            metadata=metadata or {},
        )

    @staticmethod
    def create_calculated(
        method: str,
        dependencies: List[DataLineage],
        quality: DataQuality = DataQuality.MEDIUM,
        metadata: Optional[Dict] = None,
    ) -> DataLineage:
        return DataLineage(
            source=DataSource.CALCULATED,
            quality=quality,
            timestamp=datetime.now(),
            dependencies=dependencies or [],
            calculation_method=method,
            metadata=metadata or {},
        )

    @staticmethod
    def merge_lineages(lineages: List[DataLineage], method: str) -> DataLineage:
        if not lineages:
            return LineageTracker.create_calculated(method=method, dependencies=[], quality=DataQuality.VERY_LOW)
        avg_quality = sum(lineage.quality.value for lineage in lineages) / len(lineages)
        quality = DataQuality.from_score(min(1.0, avg_quality + 0.1))
        return DataLineage(
            source=DataSource.CALCULATED,
            quality=quality,
            timestamp=datetime.now(),
            dependencies=lineages,
            calculation_method=method,
            metadata={'merged_count': len(lineages)},
        )

@dataclass
class LineageNode:
    """
    Узел в графе происхождения данных.
    Базовый строительный блок для всей системы lineage.
    """
    node_id: str
    parent_id: Optional[str]  # Для множественных родителей используем first_parent, остальные в metadata
    node_type: str  # 'snapshot', 'analysis', 'matrix_decision', 'execution', 'shadow_test', 'lab_experiment'
    timestamp: float
    context_profile_id: Optional[str]  # Ссылка на профиль рыночных условий
    metadata: Dict[str, Any] = field(default_factory=dict)
    children_ids: List[str] = field(default_factory=list)
    
    def to_dict(self):
        return asdict(self)
    
    def get_lineage_chain(self, graph: 'LineageGraph') -> List['LineageNode']:
        """Возвращает полную цепочку предков до корневого снимка."""
        chain = [self]
        current_id = self.parent_id
        while current_id and current_id in graph.nodes:
            node = graph.nodes[current_id]
            chain.append(node)
            current_id = node.parent_id
        return list(reversed(chain))


@dataclass
class LineageGraph:
    """
    Граф всех узлов lineage в памяти.
    Предоставляет методы для навигации и анализа связей.
    """
    nodes: Dict[str, LineageNode] = field(default_factory=dict)
    
    def add_node(self, node: LineageNode):
        self.nodes[node.node_id] = node
        
        # Обновляем родителя
        if node.parent_id and node.parent_id in self.nodes:
            parent = self.nodes[node.parent_id]
            if node.node_id not in parent.children_ids:
                parent.children_ids.append(node.node_id)
    
    def get_node(self, node_id: str) -> Optional[LineageNode]:
        return self.nodes.get(node_id)
    
    def get_children(self, node_id: str) -> List[LineageNode]:
        """Получить всех потомков узла."""
        if node_id not in self.nodes:
            return []
        node = self.nodes[node_id]
        return [self.nodes[cid] for cid in node.children_ids if cid in self.nodes]
    
    def get_tree(self, node_id: str, max_depth: int = 10) -> Dict:
        """Рекурсивно строит дерево наследования."""
        if node_id not in self.nodes or max_depth <= 0:
            return {}
        
        node = self.nodes[node_id]
        tree = {
            'id': node.node_id,
            'type': node.node_type,
            'timestamp': node.timestamp,
            'context': node.context_profile_id,
            'metadata': node.metadata,
            'children': []
        }
        
        for child_id in node.children_ids:
            child_tree = self.get_tree(child_id, max_depth - 1)
            if child_tree:
                tree['children'].append(child_tree)
        
        return tree
    
    def find_path(self, start_id: str, end_id: str) -> List[str]:
        """Находит путь между двумя узлами (для анализа влияния)."""
        if start_id not in self.nodes or end_id not in self.nodes:
            return []
        
        # BFS поиск
        from collections import deque
        queue = deque([(start_id, [start_id])])
        visited = {start_id}
        
        while queue:
            current_id, path = queue.popleft()
            if current_id == end_id:
                return path
            
            node = self.nodes.get(current_id)
            if node:
                for child_id in node.children_ids:
                    if child_id not in visited:
                        visited.add(child_id)
                        queue.append((child_id, path + [child_id]))
        
        return []  # Путь не найден


class DataLineageManager:
    """
    Центральный менеджер происхождения данных.
    Отвечает за создание узлов, связывание их в граф и сохранение истории.
    """
    
    def __init__(self, db_connector=None):
        self.graph = LineageGraph()
        self.active_chains: Dict[str, str] = {}  # session_id -> root_snapshot_id
        self.db_connector = db_connector
        # Кэш для быстрого доступа к последним узлам
        self._cache_size = 1000
        self._recent_nodes: List[str] = []
        
        logger.info("DataLineageManager v2.0 initialized")

    def generate_id(self, prefix: str, content_hash: Optional[str] = None) -> str:
        """Генерирует уникальный ID с префиксом и опциональным хешем содержимого."""
        if content_hash:
            short_hash = content_hash[:8]
            return f"{prefix}_{short_hash}_{int(time.time())}"
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    def create_snapshot_node(self, market_data: Dict, context_profile_id: Optional[str] = None) -> str:
        """
        Создает корневой узел для снимка рынка.
        Возвращает ID снимка, который будет передан всем дочерним анализам.
        """
        # Создаем хеш содержимого снимка для уникальности
        content_str = json.dumps(market_data, sort_keys=True)
        content_hash = hashlib.sha256(content_str.encode()).hexdigest()
        
        node_id = self.generate_id("snap", content_hash)
        
        node = LineageNode(
            node_id=node_id,
            parent_id=None,
            node_type='snapshot',
            timestamp=time.time(),
            context_profile_id=context_profile_id,
            metadata={
                "symbol": market_data.get("symbol"),
                "timeframe": market_data.get("timeframe"),
                "close_time": market_data.get("close_time"),
                "data_hash": content_hash,
                "candles_count": len(market_data.get("candles", []))
            }
        )
        
        self.graph.add_node(node)
        self._add_to_cache(node_id)
        logger.debug(f"Created snapshot node: {node_id}")
        return node_id

    def create_analysis_node(self, parent_snapshot_id: str, analyzer_name: str, 
                             result_vector: Dict, confidence: float,
                             additional_metadata: Optional[Dict] = None) -> str:
        """
        Создает узел анализа, привязанный к снимку.
        Каждый анализ получает персональный ID для отслеживания влияния.
        """
        if parent_snapshot_id not in self.graph.nodes:
            raise ValueError(f"Parent snapshot {parent_snapshot_id} not found")
            
        node_id = self.generate_id("analysis")
        parent_node = self.graph.nodes[parent_snapshot_id]
        
        # Формируем краткое описание вектора для логирования
        vector_summary = {}
        for k, v in result_vector.items():
            if isinstance(v, (int, float, str)):
                vector_summary[k] = v
            elif isinstance(v, dict):
                vector_summary[k] = str(v)[:50]
            elif isinstance(v, list):
                vector_summary[k] = f"[{len(v)} items]"
        
        metadata = {
            "analyzer": analyzer_name,
            "confidence": confidence,
            "vector_summary": vector_summary,
            "full_vector": result_vector  # Сохраняем полный вектор для детального разбора
        }
        if additional_metadata:
            metadata.update(additional_metadata)
        
        node = LineageNode(
            node_id=node_id,
            parent_id=parent_snapshot_id,
            node_type='analysis',
            timestamp=time.time(),
            context_profile_id=parent_node.context_profile_id,
            metadata=metadata
        )
        
        self.graph.add_node(node)
        self._add_to_cache(node_id)
        logger.debug(f"Created analysis node: {node_id} for {analyzer_name}")
        return node_id

    def create_matrix_decision_node(self, input_analysis_ids: List[str], 
                                    probability_field: Dict, final_vector: Dict,
                                    context_profile_id: Optional[str] = None) -> str:
        """
        Создает узел решения Матрицы вероятностей.
        У него может быть несколько родителей (разные анализы).
        В качестве parent_id берём первый анализ, но все связи хранятся в metadata.
        """
        if not input_analysis_ids:
            raise ValueError("input_analysis_ids cannot be empty")
        
        # Проверяем существование всех входных анализов
        for aid in input_analysis_ids:
            if aid not in self.graph.nodes:
                raise ValueError(f"Input analysis {aid} not found")
        
        # Берём контекст от первого анализа
        first_analysis = self.graph.nodes[input_analysis_ids[0]]
        context_id = context_profile_id or first_analysis.context_profile_id
        
        # Находим корневой снимок через первого родителя
        root_snapshot_id = input_analysis_ids[0]
        current_id = input_analysis_ids[0]
        depth = 0
        while self.graph.nodes[current_id].parent_id and depth < 20:
            current_id = self.graph.nodes[current_id].parent_id
            root_snapshot_id = current_id
            depth += 1

        node_id = self.generate_id("matrix")
        
        # Формируем краткое summary поля вероятностей
        field_summary = {}
        for scenario, data in probability_field.items():
            if isinstance(data, list):
                field_summary[scenario] = f"{len(data)} points"
            else:
                field_summary[scenario] = str(data)[:50]
        
        node = LineageNode(
            node_id=node_id,
            parent_id=root_snapshot_id,  # Логически привязываем к снимку
            node_type='matrix_decision',
            timestamp=time.time(),
            context_profile_id=context_id,
            metadata={
                "input_analyses": input_analysis_ids,  # Все родители здесь
                "probability_field_summary": field_summary,
                "final_vector": final_vector,
                "analysts_count": len(input_analysis_ids)
            }
        )
        
        # Связываем со всеми входами через children у анализов
        for aid in input_analysis_ids:
            analysis_node = self.graph.nodes[aid]
            if node_id not in analysis_node.children_ids:
                analysis_node.children_ids.append(node_id)
        
        self.graph.add_node(node)
        self._add_to_cache(node_id)
        logger.info(f"Created matrix decision node: {node_id} from {len(input_analysis_ids)} analyses")
        return node_id

    def create_execution_node(self, matrix_node_id: str, trade_params: Dict, 
                              status: str = 'pending') -> str:
        """Создает узел исполнения сделки."""
        if matrix_node_id not in self.graph.nodes:
            raise ValueError(f"Matrix node {matrix_node_id} not found")
            
        node_id = self.generate_id("exec")
        parent_node = self.graph.nodes[matrix_node_id]
        
        node = LineageNode(
            node_id=node_id,
            parent_id=matrix_node_id,
            node_type='execution',
            timestamp=time.time(),
            context_profile_id=parent_node.context_profile_id,
            metadata={
                "trade_params": trade_params,
                "status": status,
                "pnl": None,
                "exit_reason": None,
                "entry_filled": False,
                "sl_triggered": False,
                "tp_triggered": False
            }
        )
        
        self.graph.add_node(node)
        self._add_to_cache(node_id)
        logger.info(f"Created execution node: {node_id} for {trade_params.get('symbol')}")
        return node_id

    def update_execution_node(self, exec_node_id: str, updates: Dict):
        """Обновляет узел исполнения (PnL, статус, причина выхода)."""
        if exec_node_id not in self.graph.nodes:
            logger.warning(f"Execution node {exec_node_id} not found for update")
            return
        
        node = self.graph.nodes[exec_node_id]
        node.metadata.update(updates)
        logger.debug(f"Updated execution node {exec_node_id}: {updates.keys()}")

    def create_shadow_lab_node(self, original_snapshot_id: str, scenario: str, 
                               hypothetical_result: Dict, 
                               experiment_type: str = 'shadow') -> str:
        """
        Создает узел для тестов в Теневике/Лаборатории.
        experiment_type: 'shadow' или 'lab'
        """
        node_id = self.generate_id(experiment_type)
        parent_node = self.graph.nodes.get(original_snapshot_id)
        
        if not parent_node:
            # Если снимок удален из памяти, создаем сиротский узел (редкий случай)
            node = LineageNode(
                node_id=node_id,
                parent_id=original_snapshot_id,
                node_type=f'{experiment_type}_test',
                timestamp=time.time(),
                context_profile_id=None,
                metadata={
                    "scenario": scenario, 
                    "result": hypothetical_result,
                    "orphaned": True
                }
            )
        else:
            node = LineageNode(
                node_id=node_id,
                parent_id=original_snapshot_id,
                node_type=f'{experiment_type}_test',
                timestamp=time.time(),
                context_profile_id=parent_node.context_profile_id,
                metadata={
                    "scenario": scenario, 
                    "result": hypothetical_result,
                    "experiment_type": experiment_type
                }
            )
            self.graph.add_node(node)
            
        self._add_to_cache(node_id)
        logger.debug(f"Created {experiment_type} node: {node_id}")
        return node_id

    def get_lineage_tree(self, node_id: str, depth: int = 5) -> Dict:
        """Рекурсивно получает дерево наследования для узла."""
        return self.graph.get_tree(node_id, depth)

    def get_full_chain(self, node_id: str) -> List[LineageNode]:
        """Получает полную цепочку предков узла."""
        if node_id not in self.graph.nodes:
            return []
        node = self.graph.nodes[node_id]
        return node.get_lineage_chain(self.graph)

    def analyze_influence(self, snapshot_id: str, target_node_id: str) -> Dict:
        """
        Анализирует влияние конкретного снимка на целевой узел.
        Возвращает цепочку влияния и промежуточные节点.
        """
        path = self.graph.find_path(snapshot_id, target_node_id)
        if not path:
            return {"influenced": False, "path": []}
        
        nodes_chain = [self.graph.nodes[nid] for nid in path if nid in self.graph.nodes]
        
        # Считаем вклад каждого типа узлов
        influence_map = {}
        for node in nodes_chain:
            node_type = node.node_type
            if node_type not in influence_map:
                influence_map[node_type] = 0
            influence_map[node_type] += 1
        
        return {
            "influenced": True,
            "path": path,
            "nodes": nodes_chain,
            "influence_breakdown": influence_map,
            "chain_length": len(path)
        }

    def _add_to_cache(self, node_id: str):
        self._recent_nodes.append(node_id)
        if len(self._recent_nodes) > self._cache_size:
            old_id = self._recent_nodes.pop(0)
            # Авто-сохранение старых узлов в БД
            self.persist_to_db(old_id)

    def persist_to_db(self, node_id: str):
        """Метод для сохранения узла в постоянную БД (вызывается автоматически)."""
        if node_id not in self.graph.nodes:
            return
        node = self.graph.nodes[node_id]
        
        if self.db_connector:
            try:
                self.db_connector.insert('lineage_log', node.to_dict())
                logger.debug(f"Persisted node {node_id} to DB")
            except Exception as e:
                logger.error(f"Failed to persist node {node_id}: {e}")
        else:
            # Если БД нет, просто логируем
            logger.debug(f"Node {node_id} ready for persistence (no DB connector)")

    def get_statistics(self) -> Dict:
        """Статистика по графу lineage."""
        stats = {
            "total_nodes": len(self.graph.nodes),
            "by_type": {},
            "active_chains": len(self.active_chains),
            "cache_size": len(self._recent_nodes)
        }
        
        for node in self.graph.nodes.values():
            t = node.node_type
            if t not in stats["by_type"]:
                stats["by_type"][t] = 0
            stats["by_type"][t] += 1
        
        return stats

    def clear_old_nodes(self, max_age_seconds: float = 3600):
        """Очистка старых узлов из памяти (с предварительным сохранением в БД)."""
        current_time = time.time()
        to_remove = []
        
        for node_id, node in self.graph.nodes.items():
            if current_time - node.timestamp > max_age_seconds:
                to_remove.append(node_id)
        
        for node_id in to_remove:
            self.persist_to_db(node_id)
            del self.graph.nodes[node_id]
            if node_id in self._recent_nodes:
                self._recent_nodes.remove(node_id)
        
        logger.info(f"Cleared {len(to_remove)} old nodes from memory")
        return len(to_remove)


# Глобальный экземпляр (будет инициализирован в ядре)
lineage_manager = DataLineageManager()
