import json

import pytest

from prediction_core.storage.events import (
    EVENT_SCHEMA_VERSION,
    SUBJECT_JOB_REQUESTED,
    build_event_payload,
    publish_event,
    validate_event_payload,
)


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


def test_build_event_payload_sets_schema_and_paper_guards():
    payload = build_event_payload(
        event_type="job_requested",
        source="prediction_core.storage.jobs",
        occurred_at="2026-04-27T00:00:00+00:00",
        data={"job_id": "job-1"},
    )

    assert SUBJECT_JOB_REQUESTED == "prediction_core.jobs.requested"
    assert payload["schema_version"] == EVENT_SCHEMA_VERSION
    assert payload["event_type"] == "job_requested"
    assert payload["source"] == "prediction_core.storage.jobs"
    assert payload["occurred_at"] == "2026-04-27T00:00:00+00:00"
    assert payload["data"] == {"job_id": "job-1"}
    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False
    assert validate_event_payload(payload) == payload


def test_validate_event_payload_rejects_live_order_enabled():
    payload = build_event_payload(event_type="audit_recorded", data={"run_id": "r1"})
    payload["live_order_allowed"] = True

    with pytest.raises(ValueError, match="must not enable live orders"):
        validate_event_payload(payload)
