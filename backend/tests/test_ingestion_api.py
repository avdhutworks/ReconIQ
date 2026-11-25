
from uuid import uuid4


def create_source_system(client, is_active=True):
    response = client.post(
        "/api/v1/source-systems",
        json={
            "code": f"API_TEST_{uuid4().hex[:8]}",
            "name": "API Test Payment Gateway",
            "description": "Automated API test",
        },
    )

    assert response.status_code == 201

    source_id = response.json()["id"]

    if not is_active:
        deactivate_response = client.patch(
            f"/api/v1/source-systems/{source_id}/deactivate"
        )
        assert deactivate_response.status_code == 200

    return source_id


def create_transaction(transaction_id, amount="1500.00"):
    return {
        "external_transaction_id": transaction_id,
        "amount": amount,
        "currency": "INR",
        "transaction_type": "PAYMENT",
        "transaction_timestamp": "2026-11-24T10:30:00+05:30",
        "raw_payload": {
            "gateway_reference": f"GW-{transaction_id}",
            "merchant_id": "MERCHANT-TEST-001",
            "payment_method": "UPI",
            "gateway_status": "SUCCESS",
            "settlement_status": "PENDING",
        },
    }


def create_ingestion_payload(
    source_id,
    idempotency_key="API-TEST-BATCH-001",
    transactions=None,
):
    if transactions is None:
        transactions = [
            create_transaction("API-TXN-001")
        ]

    return {
        "source_system_id": source_id,
        "idempotency_key": idempotency_key,
        "transactions": transactions,
    }


def test_successful_ingestion_api(client):
    source_id = create_source_system(client)

    payload = create_ingestion_payload(source_id)

    response = client.post(
        "/api/v1/ingestion/batches",
        json=payload,
    )

    assert response.status_code == 201
    assert response.headers["X-Idempotent-Replay"] == "false"

    data = response.json()

    assert data["source_system_id"] == source_id
    assert data["idempotency_key"] == "API-TEST-BATCH-001"
    assert data["total_records"] == 1
    assert data["accepted_records"] == 1
    assert data["duplicate_records"] == 0
    assert len(data["transactions"]) == 1


def test_idempotent_replay_api(client):
    source_id = create_source_system(client)

    payload = create_ingestion_payload(source_id)

    first_response = client.post(
        "/api/v1/ingestion/batches",
        json=payload,
    )

    second_response = client.post(
        "/api/v1/ingestion/batches",
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 200

    assert second_response.headers["X-Idempotent-Replay"] == "true"

    assert (
        first_response.json()["id"]
        == second_response.json()["id"]
    )


def test_idempotency_conflict_api(client):
    source_id = create_source_system(client)

    first_payload = create_ingestion_payload(
        source_id,
        idempotency_key="API-CONFLICT-001",
        transactions=[
            create_transaction("API-CONFLICT-TXN", "1500.00")
        ],
    )

    changed_payload = create_ingestion_payload(
        source_id,
        idempotency_key="API-CONFLICT-001",
        transactions=[
            create_transaction("API-CONFLICT-TXN", "2500.00")
        ],
    )

    first_response = client.post(
        "/api/v1/ingestion/batches",
        json=first_payload,
    )

    conflict_response = client.post(
        "/api/v1/ingestion/batches",
        json=changed_payload,
    )

    assert first_response.status_code == 201
    assert conflict_response.status_code == 409

    assert conflict_response.json()["detail"] == (
        "Idempotency key already exists with a different payload."
    )


def test_duplicate_transaction_api(client):
    source_id = create_source_system(client)

    first_payload = create_ingestion_payload(
        source_id,
        idempotency_key="API-DUPLICATE-001",
        transactions=[
            create_transaction("API-DUPLICATE-TXN")
        ],
    )

    second_payload = create_ingestion_payload(
        source_id,
        idempotency_key="API-DUPLICATE-002",
        transactions=[
            create_transaction("API-DUPLICATE-TXN"),
            create_transaction("API-NEW-TXN", "2500.00"),
        ],
    )

    first_response = client.post(
        "/api/v1/ingestion/batches",
        json=first_payload,
    )

    second_response = client.post(
        "/api/v1/ingestion/batches",
        json=second_payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201

    data = second_response.json()

    assert data["total_records"] == 2
    assert data["accepted_records"] == 1
    assert data["duplicate_records"] == 1
    assert len(data["transactions"]) == 1
    assert (
        data["transactions"][0]["external_transaction_id"]
        == "API-NEW-TXN"
    )


def test_unknown_source_system_api(client):
    payload = create_ingestion_payload(str(uuid4()))

    response = client.post(
        "/api/v1/ingestion/batches",
        json=payload,
    )

    assert response.status_code == 404


def test_inactive_source_system_api(client):
    source_id = create_source_system(
        client,
        is_active=False,
    )

    payload = create_ingestion_payload(source_id)

    response = client.post(
        "/api/v1/ingestion/batches",
        json=payload,
    )

    assert response.status_code == 409


def test_empty_transaction_list_rejected(client):
    source_id = create_source_system(client)

    payload = create_ingestion_payload(
        source_id,
        transactions=[],
    )

    response = client.post(
        "/api/v1/ingestion/batches",
        json=payload,
    )

    assert response.status_code == 422


def test_invalid_transaction_type_rejected(client):
    source_id = create_source_system(client)

    transaction = create_transaction("INVALID-TYPE-TXN")
    transaction["transaction_type"] = "INVALID"

    payload = create_ingestion_payload(
        source_id,
        transactions=[transaction],
    )

    response = client.post(
        "/api/v1/ingestion/batches",
        json=payload,
    )

    assert response.status_code == 422


def test_timezone_missing_timestamp_rejected(client):
    source_id = create_source_system(client)

    transaction = create_transaction("INVALID-TIMESTAMP-TXN")
    transaction["transaction_timestamp"] = "2026-11-24T10:30:00"

    payload = create_ingestion_payload(
        source_id,
        transactions=[transaction],
    )

    response = client.post(
        "/api/v1/ingestion/batches",
        json=payload,
    )

    assert response.status_code == 422


def test_list_ingestion_batches_api(client):
    source_id = create_source_system(client)

    payload = create_ingestion_payload(source_id)

    client.post(
        "/api/v1/ingestion/batches",
        json=payload,
    )

    response = client.get("/api/v1/ingestion/batches")

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 1
    assert len(data["items"]) == 1


def test_get_ingestion_batch_details_api(client):
    source_id = create_source_system(client)

    payload = create_ingestion_payload(source_id)

    create_response = client.post(
        "/api/v1/ingestion/batches",
        json=payload,
    )

    batch_id = create_response.json()["id"]

    response = client.get(
        f"/api/v1/ingestion/batches/{batch_id}"
    )

    assert response.status_code == 200
    assert response.json()["id"] == batch_id
    assert len(response.json()["transactions"]) == 1


def test_get_nonexistent_batch_api(client):
    response = client.get(
        f"/api/v1/ingestion/batches/{uuid4()}"
    )

    assert response.status_code == 404


def test_list_raw_transactions_api(client):
    source_id = create_source_system(client)

    payload = create_ingestion_payload(
        source_id,
        transactions=[
            create_transaction("RAW-TXN-001"),
            create_transaction("RAW-TXN-002", "2500.00"),
        ],
    )

    client.post(
        "/api/v1/ingestion/batches",
        json=payload,
    )

    response = client.get("/api/v1/raw-transactions")

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_get_raw_transaction_details_api(client):
    source_id = create_source_system(client)

    payload = create_ingestion_payload(
        source_id,
        transactions=[
            create_transaction("RAW-DETAIL-TXN")
        ],
    )

    create_response = client.post(
        "/api/v1/ingestion/batches",
        json=payload,
    )

    transaction_id = (
        create_response.json()["transactions"][0]["id"]
    )

    response = client.get(
        f"/api/v1/raw-transactions/{transaction_id}"
    )

    assert response.status_code == 200
    assert response.json()["id"] == transaction_id
    assert (
        response.json()["external_transaction_id"]
        == "RAW-DETAIL-TXN"
    )


def test_get_nonexistent_raw_transaction_api(client):
    response = client.get(
        f"/api/v1/raw-transactions/{uuid4()}"
    )

    assert response.status_code == 404
