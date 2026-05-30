"""System supervisor skeleton.

Owns liveness: config load, event log, data connections, cycle runner, reconnects and graceful shutdown.
"""

class SystemSupervisor:
    def run(self) -> None:
        raise NotImplementedError("Wire NOVA runtime services and start cycle loop")

