"""Reconnect/backfill policy skeleton."""

class ReconnectPolicy:
    def on_disconnect(self) -> object:
        raise NotImplementedError

