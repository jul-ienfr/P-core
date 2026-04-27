import json

import pytest

from prediction_core.storage.events import publish_event


class FakeNatsClient:
    def __init__(self):
        self.published = []

    async def publish(self, subject, payload):
        self.published.append((subject, payload))


@pytest.mark.asyncio
async def test_publish_event_adds_paper_flags():
    client = FakeNatsClient()

    await publish_event(client, "prediction_core.test", {"value": 1})

    subject, payload = client.published[0]
    data = json.loads(payload.decode("utf-8"))
    assert subject == "prediction_core.test"
    assert data["paper_only"] is True
    assert data["live_order_allowed"] is False
    assert data["value"] == 1
