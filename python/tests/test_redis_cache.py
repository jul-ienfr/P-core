from prediction_core.polymarket_marketdata import MarketDataSnapshot
from prediction_core.storage.redis_cache import RedisMarketDataCacheSink, set_short_ttl_idempotency


class FakeRedis:
    def __init__(self):
        self.calls = []

    def set(self, *args):
        self.calls.append(("set", args))

    def setex(self, *args):
        self.calls.append(("setex", args))


def test_redis_marketdata_sink_writes_snapshot_json():
    redis = FakeRedis()
    sink = RedisMarketDataCacheSink(redis, ttl_seconds=30)

    sink(MarketDataSnapshot(token_id="token", best_bid=0.4, best_ask=0.5, spread=0.1, bid_depth=1.0, ask_depth=2.0))

    assert redis.calls[0][0] == "setex"
    assert redis.calls[0][1][0] == "pcore:marketdata:snapshot:token"
    assert redis.calls[0][1][1] == 30


def test_set_short_ttl_idempotency_uses_nx():
    class RedisNx:
        def set(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            return True

    redis = RedisNx()

    assert set_short_ttl_idempotency(redis, "abc") is True
    assert redis.args == ("pcore:idempotency:abc", "1")
    assert redis.kwargs["nx"] is True
