
from datetime import datetime, timezone
from uuid import uuid4

import pytest


INGESTION_URL = "/api/v1/ingestion/batches"


def build_payload(source_system_id, idempotency_key=None):
    return {
        "source_system_id": str(source_system_id),
        "idempotency_key": idempotency_key or f"TEST-{uuid4()}",
        "transactions": [
            {
                "external_transaction_id": f"TXN-{uuid4()}",
                "amount": "1500.00",
                "currency": "INR",
                "transaction_type": "PAYMENT",
                "transaction_timestamp": datetime.now(
                    timezone.utc
                ).isoformat(),
                "raw_payload": {
                    "reference": "RECONIQ-TEST",
                    "channel": "UPI",
                },
            }
        ],
    }


def test_successful_ingestion(client, source_system_id):
    payload = build_payload(source_system_id)

    response = client.post(INGESTION_URL, json=payload)

    assert response.status_code == 201

    body = response.json()

    assert body["total_records"] == 1
    assert body["accepted_records"] == 1
    assert body["duplicate_records"] == 0

    assert response.headers["X-Idempotent-Replay"] == "false"


def test_idempotent_replay(client, source_system_id):
    payload = build_payload(source_system_id)

    original = client.post(INGESTION_URL, json=payload)
    replay = client.post(INGESTION_URL, json=payload)

    assert original.status_code == 201
    assert replay.status_code == 200

    assert original.json() == replay.json()

    assert original.headers["X-Idempotent-Replay"] == "false"
    assert replay.headers["X-Idempotent-Replay"] == "true"


def test_idempotency_conflict(client, source_system_id):
    payload = build_payload(
        source_system_id,
        idempotency_key=f"CONFLICT-{uuid4()}",
    )

    original = client.post(INGESTION_URL, json=payload)

    assert original.status_code == 201

    changed_payload = {
        **payload,
        "transactions": [
            {
                **payload["transactions"][0],
                "amount": "2500.00",
            }
        ],
    }

    conflict = client.post(
        INGESTION_URL,
        json=changed_payload,
    )

    assert conflict.status_code == 409


def test_duplicate_transactions_in_same_batch(
    client,
    source_system_id,
):
    transaction = {
        "external_transaction_id": f"DUP-{uuid4()}",
        "amount": "1000.00",
        "currency": "INR",
        "transaction_type": "PAYMENT",
        "transaction_timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "raw_payload": {"reference": "DUPLICATE-TEST"},
    }

    payload = {
        "source_system_id": str(source_system_id),
        "idempotency_key": f"DUP-BATCH-{uuid4()}",
        "transactions": [
            transaction,
            transaction,
        ],
    }

    response = client.post(INGESTION_URL, json=payload)

    assert response.status_code == 201

    body = response.json()

    assert body["total_records"] == 2
    assert body["accepted_records"] == 1
    assert body["duplicate_records"] == 1
