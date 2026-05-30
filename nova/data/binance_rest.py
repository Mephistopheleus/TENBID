"""REST client skeleton for warmup, backfill, reconciliation, orderbook probes and aggTrades replay."""

class BinanceRestClient:
    def get_klines(self, *args: object, **kwargs: object) -> object:
        raise NotImplementedError

