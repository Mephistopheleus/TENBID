"""SQLite history database for the first runnable NOVA runtime.

JSONL EventLog is the append-only journal; SQLite provides queryable memory.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from nova.analysis.models import AnalysisResult, StateContribution
from nova.analyzers.contracts import AnalysisPackage
from nova.autotune.models import AutotuneEvidence, AutotuneRecommendation
from nova.cards.models import CardDeck, EvidenceCard
from nova.core.events import Event
from nova.core.state_snapshot import StateSnapshot
from nova.data.models import MarketSnapshot
from nova.decision.trade_plan import TradePlan
from nova.matrix.models import ForecastContribution, ForecastMatrix, MatrixZone, StateMatrix
from nova.shadow.outcome import OutcomeResult, ResolutionMethod, ScenarioOutcome


SCHEMA_VERSION = 1


class HistoryDB:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    run_id TEXT,
                    cycle_id TEXT,
                    source TEXT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_plans (
                    plan_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    run_id TEXT,
                    cycle_id TEXT,
                    decision TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS market_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    primary_symbol TEXT NOT NULL,
                    base_timeframe TEXT NOT NULL,
                    quality_score REAL NOT NULL,
                    is_usable INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_results (
                    analysis_result_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    cycle_id TEXT NOT NULL,
                    analyzer_name TEXT NOT NULL,
                    analyzer_version TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    evidence_tier TEXT NOT NULL,
                    feedback_depth INTEGER NOT NULL,
                    input_matrix_id TEXT,
                    status TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    quality REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence_cards (
                    card_id TEXT PRIMARY KEY,
                    cycle_id TEXT NOT NULL,
                    card_type TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    feedback_depth INTEGER NOT NULL,
                    input_matrix_id TEXT,
                    source_analysis_result_id TEXT,
                    source_analyzer TEXT,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS forecast_contributions (
                    contribution_id TEXT PRIMARY KEY,
                    cycle_id TEXT,
                    symbol TEXT NOT NULL,
                    source_analysis_result_id TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    horizon_min INTEGER NOT NULL,
                    price_low REAL NOT NULL,
                    price_high REAL NOT NULL,
                    probability REAL NOT NULL,
                    confidence REAL NOT NULL,
                    direction TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    evidence_tier TEXT NOT NULL,
                    feedback_depth INTEGER NOT NULL,
                    input_matrix_id TEXT,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS state_contributions (
                    state_contribution_id TEXT PRIMARY KEY,
                    cycle_id TEXT,
                    source_analysis_result_id TEXT NOT NULL,
                    state_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    evidence_tier TEXT NOT NULL,
                    feedback_depth INTEGER NOT NULL,
                    input_matrix_id TEXT,
                    payload_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS forecast_matrices (
                    matrix_id TEXT PRIMARY KEY,
                    cycle_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    matrix_layer TEXT NOT NULL,
                    primary_only INTEGER NOT NULL,
                    zone_count INTEGER NOT NULL,
                    contributor_count INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS matrix_zones (
                    zone_id TEXT PRIMARY KEY,
                    matrix_id TEXT NOT NULL,
                    cycle_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    field_role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    horizon_min INTEGER NOT NULL,
                    price_low REAL NOT NULL,
                    price_high REAL NOT NULL,
                    scenario TEXT NOT NULL,
                    probability REAL NOT NULL,
                    confidence REAL NOT NULL,
                    agreement_score REAL NOT NULL,
                    conflict_score REAL NOT NULL,
                    importance_score REAL NOT NULL,
                    payload_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS state_matrices (
                    matrix_id TEXT PRIMARY KEY,
                    cycle_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    trust_score REAL NOT NULL,
                    volatility_state TEXT NOT NULL,
                    conflict_score REAL NOT NULL,
                    data_quality REAL NOT NULL,
                    liquidity_state TEXT,
                    payload_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS state_snapshots (
                    state_snapshot_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    cycle_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    market_snapshot_id TEXT,
                    training_role TEXT NOT NULL,
                    data_quality REAL NOT NULL,
                    data_usable INTEGER NOT NULL,
                    conflict_score REAL NOT NULL,
                    payload_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scenario_outcomes (
                    outcome_id TEXT PRIMARY KEY,
                    scenario_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    result TEXT NOT NULL,
                    gross_pnl_pct REAL NOT NULL,
                    net_pnl_pct REAL NOT NULL,
                    mfe_pct REAL NOT NULL,
                    mae_pct REAL NOT NULL,
                    duration_sec INTEGER NOT NULL,
                    resolution_method TEXT NOT NULL,
                    quality REAL NOT NULL,
                    traceable INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                )
                """
            )
            self._ensure_column(conn, "scenario_outcomes", "created_at", "TEXT")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS autotune_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_weight REAL NOT NULL,
                    profile_id TEXT NOT NULL,
                    plan_id TEXT,
                    scenario_id TEXT,
                    risk_decision_id TEXT,
                    executor_result_id TEXT,
                    payload_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS autotune_recommendations (
                    recommendation_id TEXT PRIMARY KEY,
                    target_profile_id TEXT NOT NULL,
                    sample_size INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    reason TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS active_positions (
                    position_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    status TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    scenario_id TEXT,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL,
                    take_profit REAL,
                    opened_at TEXT NOT NULL,
                    last_seen_at TEXT,
                    closed_at TEXT,
                    payload_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                )
                """
            )
            self._ensure_column(conn, "state_snapshots", "run_id", "TEXT")
            for statement in self._index_statements():
                conn.execute(statement)

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_type: str) -> None:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}
        if column_name not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

    @staticmethod
    def _index_statements() -> Iterable[str]:
        return [
            "CREATE INDEX IF NOT EXISTS idx_analysis_cycle ON analysis_results(cycle_id)",
            "CREATE INDEX IF NOT EXISTS idx_cards_cycle ON evidence_cards(cycle_id)",
            "CREATE INDEX IF NOT EXISTS idx_cards_source_analysis ON evidence_cards(source_analysis_result_id)",
            "CREATE INDEX IF NOT EXISTS idx_forecast_source_analysis ON forecast_contributions(source_analysis_result_id)",
            "CREATE INDEX IF NOT EXISTS idx_matrix_zones_matrix ON matrix_zones(matrix_id)",
            "CREATE INDEX IF NOT EXISTS idx_market_snapshots_symbol ON market_snapshots(primary_symbol)",
            "CREATE INDEX IF NOT EXISTS idx_state_snapshots_run ON state_snapshots(run_id)",
            "CREATE INDEX IF NOT EXISTS idx_state_snapshots_cycle ON state_snapshots(cycle_id)",
            "CREATE INDEX IF NOT EXISTS idx_scenario_outcomes_scenario ON scenario_outcomes(scenario_id)",
            "CREATE INDEX IF NOT EXISTS idx_scenario_outcomes_traceable ON scenario_outcomes(traceable)",
            "CREATE INDEX IF NOT EXISTS idx_scenario_outcomes_result ON scenario_outcomes(result)",
            "CREATE INDEX IF NOT EXISTS idx_autotune_evidence_scenario ON autotune_evidence(scenario_id)",
            "CREATE INDEX IF NOT EXISTS idx_autotune_recommendations_profile ON autotune_recommendations(target_profile_id)",
            "CREATE INDEX IF NOT EXISTS idx_active_positions_status_symbol ON active_positions(status, symbol)",
        ]

    def log_event(self, event: Event) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO events (
                    event_id, timestamp, run_id, cycle_id, source, event_type, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.timestamp,
                    event.run_id,
                    event.cycle_id,
                    event.source,
                    event.event_type,
                    json.dumps(event.payload, ensure_ascii=False, default=str),
                ),
            )

    def log_trade_plan(self, plan: TradePlan, run_id: str, cycle_id: str) -> None:
        payload: Dict[str, Any] = asdict(plan)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO trade_plans (
                    plan_id, run_id, cycle_id, decision, symbol, reason, profile_id, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.plan_id,
                    run_id,
                    cycle_id,
                    plan.decision,
                    plan.symbol,
                    plan.reason,
                    plan.profile_id,
                    json.dumps(payload, ensure_ascii=False, default=str),
                ),
            )

    def upsert_active_position(self, payload: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO active_positions (
                    position_id, symbol, status, plan_id, scenario_id, side, quantity,
                    entry_price, stop_loss, take_profit, opened_at, last_seen_at,
                    closed_at, payload_json, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(payload["position_id"]),
                    str(payload["symbol"]).upper(),
                    str(payload["status"]),
                    str(payload["plan_id"]),
                    payload.get("scenario_id"),
                    str(payload["side"]),
                    float(payload["quantity"]),
                    float(payload["entry_price"]),
                    payload.get("stop_loss"),
                    payload.get("take_profit"),
                    str(payload["opened_at"]),
                    payload.get("last_seen_at"),
                    payload.get("closed_at"),
                    self._json(payload),
                    SCHEMA_VERSION,
                ),
            )

    def active_position_records(self, symbol: str | None = None) -> List[Dict[str, Any]]:
        query = "SELECT payload_json FROM active_positions WHERE status = 'OPEN'"
        params: list[object] = []
        if symbol is not None:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        query += " ORDER BY opened_at ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def mark_active_position_closed(self, position_id: str, *, closed_at: str, payload_extra: Dict[str, Any] | None = None) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload_json FROM active_positions WHERE position_id = ?", (position_id,)).fetchone()
            if row is None:
                return
            payload = json.loads(row["payload_json"])
            payload.update(payload_extra or {})
            payload["status"] = "CLOSED"
            payload["closed_at"] = closed_at
            conn.execute(
                """
                UPDATE active_positions
                SET status = 'CLOSED', closed_at = ?, payload_json = ?
                WHERE position_id = ?
                """,
                (closed_at, self._json(payload), position_id),
            )

    def log_market_snapshot(self, snapshot: MarketSnapshot) -> None:
        payload = asdict(snapshot)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO market_snapshots (
                    snapshot_id, created_at, primary_symbol, base_timeframe,
                    quality_score, is_usable, payload_json, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.created_at,
                    snapshot.primary_symbol,
                    snapshot.base_timeframe,
                    snapshot.quality.score,
                    int(snapshot.quality.is_usable),
                    self._json(payload),
                    SCHEMA_VERSION,
                ),
            )

    def log_state_snapshot(self, snapshot: StateSnapshot) -> None:
        payload = asdict(snapshot)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO state_snapshots (
                    state_snapshot_id, run_id, cycle_id, symbol, stage, created_at,
                    market_snapshot_id, training_role, data_quality, data_usable,
                    conflict_score, payload_json, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.state_snapshot_id,
                    snapshot.run_id,
                    snapshot.cycle_id,
                    snapshot.symbol,
                    snapshot.stage,
                    snapshot.created_at,
                    snapshot.market_snapshot_id,
                    snapshot.training_role,
                    snapshot.data_quality,
                    int(snapshot.data_usable),
                    snapshot.conflict_score,
                    self._json(payload),
                    SCHEMA_VERSION,
                ),
            )

    def log_analysis_result(self, result: AnalysisResult) -> None:
        payload = asdict(result)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO analysis_results (
                    analysis_result_id, run_id, cycle_id, analyzer_name, analyzer_version,
                    symbol, timeframe, stage, evidence_tier, feedback_depth,
                    input_matrix_id, status, confidence, quality, created_at,
                    payload_json, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.analysis_result_id,
                    result.run_id,
                    result.cycle_id,
                    result.analyzer_name,
                    result.analyzer_version,
                    result.symbol,
                    result.timeframe,
                    result.stage,
                    result.evidence_tier,
                    result.feedback_depth,
                    result.input_matrix_id,
                    result.status,
                    result.confidence,
                    result.quality,
                    result.created_at,
                    self._json(payload),
                    SCHEMA_VERSION,
                ),
            )

    def log_evidence_card(self, card: EvidenceCard) -> None:
        payload = asdict(card)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO evidence_cards (
                    card_id, cycle_id, card_type, stage, tier, feedback_depth,
                    input_matrix_id, source_analysis_result_id, source_analyzer,
                    created_at, payload_json, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card.card_id,
                    card.cycle_id,
                    card.card_type,
                    card.stage,
                    card.tier,
                    card.feedback_depth,
                    card.input_matrix_id,
                    card.source_analysis_result_id,
                    card.source_analyzer,
                    card.created_at,
                    self._json(payload),
                    SCHEMA_VERSION,
                ),
            )

    def log_card_deck(self, deck: CardDeck) -> None:
        for card in deck.cards:
            self.log_evidence_card(card)

    def log_forecast_contribution(self, contribution: ForecastContribution, cycle_id: str | None = None) -> None:
        payload = asdict(contribution)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO forecast_contributions (
                    contribution_id, cycle_id, symbol, source_analysis_result_id,
                    timeframe, horizon_min, price_low, price_high, probability,
                    confidence, direction, stage, evidence_tier, feedback_depth,
                    input_matrix_id, created_at, payload_json, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    contribution.contribution_id,
                    cycle_id,
                    contribution.symbol,
                    contribution.source_analysis_result_id,
                    contribution.timeframe,
                    contribution.horizon_min,
                    contribution.price_low,
                    contribution.price_high,
                    contribution.probability,
                    contribution.confidence,
                    contribution.direction,
                    contribution.stage,
                    contribution.evidence_tier,
                    contribution.feedback_depth,
                    contribution.input_matrix_id,
                    contribution.created_at,
                    self._json(payload),
                    SCHEMA_VERSION,
                ),
            )

    def log_state_contribution(self, contribution: StateContribution, cycle_id: str | None = None) -> None:
        payload = asdict(contribution)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO state_contributions (
                    state_contribution_id, cycle_id, source_analysis_result_id,
                    state_type, severity, stage, evidence_tier, feedback_depth,
                    input_matrix_id, payload_json, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    contribution.state_contribution_id,
                    cycle_id,
                    contribution.source_analysis_result_id,
                    contribution.state_type,
                    contribution.severity,
                    contribution.stage,
                    contribution.evidence_tier,
                    contribution.feedback_depth,
                    contribution.input_matrix_id,
                    self._json(payload),
                    SCHEMA_VERSION,
                ),
            )

    def log_analysis_package(self, package: AnalysisPackage) -> None:
        self.log_analysis_result(package.analysis_result)
        self.log_card_deck(package.card_deck)
        for contribution in package.forecast_contributions:
            self.log_forecast_contribution(contribution, cycle_id=package.analysis_result.cycle_id)
        for contribution in package.state_contributions:
            self.log_state_contribution(contribution, cycle_id=package.analysis_result.cycle_id)

    def log_forecast_matrix(self, matrix: ForecastMatrix) -> None:
        payload = asdict(matrix)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO forecast_matrices (
                    matrix_id, cycle_id, symbol, matrix_layer, primary_only,
                    zone_count, contributor_count, payload_json, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    matrix.matrix_id,
                    matrix.cycle_id,
                    matrix.symbol,
                    matrix.matrix_layer,
                    int(matrix.primary_only),
                    len(matrix.zones),
                    len(matrix.contributor_ids),
                    self._json(payload),
                    SCHEMA_VERSION,
                ),
            )
            for zone in matrix.zones:
                self._log_matrix_zone(conn, matrix, zone)

    def _log_matrix_zone(self, conn: sqlite3.Connection, matrix: ForecastMatrix, zone: MatrixZone) -> None:
        conn.execute(
            """
            INSERT OR REPLACE INTO matrix_zones (
                zone_id, matrix_id, cycle_id, symbol, field_role, status,
                horizon_min, price_low, price_high, scenario, probability,
                confidence, agreement_score, conflict_score, importance_score,
                payload_json, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                zone.zone_id,
                matrix.matrix_id,
                matrix.cycle_id,
                matrix.symbol,
                zone.field_role,
                zone.status,
                zone.horizon_min,
                zone.price_low,
                zone.price_high,
                zone.scenario,
                zone.probability,
                zone.confidence,
                zone.agreement_score,
                zone.conflict_score,
                zone.importance_score,
                self._json(asdict(zone)),
                SCHEMA_VERSION,
            ),
        )

    def log_state_matrix(self, matrix: StateMatrix) -> None:
        payload = asdict(matrix)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO state_matrices (
                    matrix_id, cycle_id, symbol, trust_score, volatility_state,
                    conflict_score, data_quality, liquidity_state, payload_json,
                    schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    matrix.matrix_id,
                    matrix.cycle_id,
                    matrix.symbol,
                    matrix.trust_score,
                    matrix.volatility_state,
                    matrix.conflict_score,
                    matrix.data_quality,
                    matrix.liquidity_state,
                    self._json(payload),
                    SCHEMA_VERSION,
                ),
            )

    def log_scenario_outcome(self, outcome: ScenarioOutcome) -> None:
        payload = asdict(outcome)
        traceable = self._is_traceable_outcome(outcome)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO scenario_outcomes (
                    outcome_id, scenario_id, source_type, result, gross_pnl_pct,
                    net_pnl_pct, mfe_pct, mae_pct, duration_sec,
                    resolution_method, quality, traceable, created_at,
                    payload_json, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    outcome.outcome_id,
                    outcome.scenario_id,
                    outcome.source_type,
                    outcome.result,
                    outcome.gross_pnl_pct,
                    outcome.net_pnl_pct,
                    outcome.mfe_pct,
                    outcome.mae_pct,
                    outcome.duration_sec,
                    outcome.resolution_method,
                    outcome.quality,
                    int(traceable),
                    outcome.created_at,
                    self._json(payload),
                    SCHEMA_VERSION,
                ),
            )

    def log_autotune_evidence(self, evidence: AutotuneEvidence) -> None:
        payload = asdict(evidence)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO autotune_evidence (
                    evidence_id, source_type, source_weight, profile_id, plan_id,
                    scenario_id, risk_decision_id, executor_result_id,
                    payload_json, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.evidence_id,
                    evidence.source_type,
                    evidence.source_weight,
                    evidence.profile_id,
                    evidence.plan_id,
                    evidence.scenario_id,
                    evidence.risk_decision_id,
                    evidence.executor_result_id,
                    self._json(payload),
                    SCHEMA_VERSION,
                ),
            )

    def log_autotune_recommendation(self, recommendation: AutotuneRecommendation) -> None:
        payload = asdict(recommendation)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO autotune_recommendations (
                    recommendation_id, target_profile_id, sample_size,
                    confidence, reason, payload_json, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recommendation.recommendation_id,
                    recommendation.target_profile_id,
                    recommendation.sample_size,
                    recommendation.confidence,
                    recommendation.reason,
                    self._json(payload),
                    SCHEMA_VERSION,
                ),
            )

    def traceable_outcomes(self, source_type: str | None = None, limit: int = 500) -> List[ScenarioOutcome]:
        query = "SELECT payload_json FROM scenario_outcomes WHERE traceable = 1"
        params: list[object] = []
        if source_type is not None:
            query += " AND source_type = ?"
            params.append(source_type)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._outcome_from_payload(json.loads(row["payload_json"])) for row in rows]

    def pending_outcomes(self, limit: int = 100) -> List[ScenarioOutcome]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM scenario_outcomes
                WHERE result = ? AND resolution_method = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (OutcomeResult.PENDING, ResolutionMethod.PENDING, limit),
            ).fetchall()
        return [self._outcome_from_payload(json.loads(row["payload_json"])) for row in rows]

    def latest_outcome_for_scenario(self, scenario_id: str) -> Optional[ScenarioOutcome]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM scenario_outcomes
                WHERE scenario_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (scenario_id,),
            ).fetchone()
        if row is None:
            return None
        return self._outcome_from_payload(json.loads(row["payload_json"]))

    def count_traceable_outcomes(self, source_type: str | None = None) -> int:
        query = "SELECT COUNT(*) FROM scenario_outcomes WHERE traceable = 1"
        params: list[str] = []
        if source_type is not None:
            query += " AND source_type = ?"
            params.append(source_type)
        with self._connect() as conn:
            return int(conn.execute(query, params).fetchone()[0])

    @staticmethod
    def _is_traceable_outcome(outcome: ScenarioOutcome) -> bool:
        if outcome.quality <= 0:
            return False
        traceable_methods = {
            ResolutionMethod.TESTNET_CLOSE,
            ResolutionMethod.POSITION_MANAGER_CLOSE,
            ResolutionMethod.OHLC_CLEAR,
            ResolutionMethod.ONE_MINUTE_REPLAY,
            ResolutionMethod.AGGTRADES_REPLAY,
        }
        if outcome.resolution_method not in traceable_methods:
            return False
        return outcome.result not in {OutcomeResult.PENDING, OutcomeResult.UNRESOLVED}

    @staticmethod
    def _outcome_from_payload(payload: Dict[str, Any]) -> ScenarioOutcome:
        return ScenarioOutcome(
            scenario_id=str(payload["scenario_id"]),
            source_type=str(payload["source_type"]),
            result=str(payload["result"]),
            gross_pnl_pct=float(payload["gross_pnl_pct"]),
            net_pnl_pct=float(payload["net_pnl_pct"]),
            mfe_pct=float(payload["mfe_pct"]),
            mae_pct=float(payload["mae_pct"]),
            duration_sec=int(payload["duration_sec"]),
            resolution_method=str(payload["resolution_method"]),
            quality=float(payload["quality"]),
            planned_costs=dict(payload.get("planned_costs") or {}),
            actual_costs=dict(payload.get("actual_costs") or {}),
            payload=dict(payload.get("payload") or {}),
            outcome_id=str(payload["outcome_id"]),
            created_at=str(payload.get("created_at") or ""),
            notes=payload.get("notes"),
        )

    @staticmethod
    def _json(payload: Dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, default=str)
