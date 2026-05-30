"""System supervisor.

Owns liveness: config load, event log, data connections, cycle runner,
reconnects and graceful shutdown. The first runtime implementation is
intentionally small: it validates TESTNET mode and runs one HOLD cycle.
"""

from __future__ import annotations

from pathlib import Path

from nova.core.config_loader import ConfigLoader, RuntimeConfig
from nova.core.event_log import EventLog
from nova.core.events import Event, EventTypes
from nova.core.history_db import HistoryDB
from nova.core.ids import RUN, new_id
from nova.core.safety_kernel import SafetyKernel
from nova.supervisor.cycle_runner import CycleRunner


class SystemSupervisor:
    def __init__(self, root_dir: str | Path = ".") -> None:
        self.root_dir = Path(root_dir).resolve()

    def run(self) -> None:
        config = ConfigLoader(self.root_dir).load()
        self._validate_safety(config)

        run_id = new_id(RUN)
        event_log = EventLog(str(config.event_log_path))
        history_db = HistoryDB(config.sqlite_path)

        self._record(
            event_log,
            history_db,
            Event(
                event_type=EventTypes.SYSTEM_STARTED,
                run_id=run_id,
                source="SystemSupervisor",
                payload={
                    "trading_mode": config.trading_mode,
                    "symbol": config.symbol,
                    "base_timeframe": config.base_timeframe,
                    "profile_id": config.profile.profile_id,
                },
            ),
        )
        self._record(
            event_log,
            history_db,
            Event(
                event_type=EventTypes.CONFIG_LOADED,
                run_id=run_id,
                source="SystemSupervisor",
                payload={
                    "event_log_path": str(config.event_log_path),
                    "sqlite_path": str(config.sqlite_path),
                    "synthetic_timeframes": config.synthetic_timeframes,
                    "warmup_candles": config.warmup_candles,
                },
            ),
        )
        self._record(
            event_log,
            history_db,
            Event(
                event_type=EventTypes.PROFILE_APPLIED,
                run_id=run_id,
                source="SystemSupervisor",
                payload=config.profile.to_dict(),
            ),
        )

        plan = CycleRunner(
            run_id=run_id,
            config=config,
            event_log=event_log,
            history_db=history_db,
        ).run_once()

        print(f"NOVA run {run_id} completed: {plan.decision} ({plan.reason})")

    @staticmethod
    def _validate_safety(config: RuntimeConfig) -> None:
        kernel = SafetyKernel()
        kernel.assert_mode_allowed(config.trading_mode, live_unlock=config.live_unlock)
        kernel.assert_symbol_allowed(config.symbol)

    @staticmethod
    def _record(event_log: EventLog, history_db: HistoryDB, event: Event) -> None:
        event_log.append(event)
        history_db.log_event(event)
