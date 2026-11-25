
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models.source_system import SourceSystem
from app.modules.ingestion.schemas import PaymentIngestionRequest
from app.modules.ingestion.service import (
    IdempotencyConflictError,
    PaymentIngestionService,
    SourceSystemInactiveError,
    SourceSystemNotFoundError,
)


def create_source_system(db, is_active=True):
    source = SourceSystem(
        code=f"TEST_{uuid4().hex[:8]}",
        name="Test Payment Gateway",
        description="Ingestion service test",
        is_active=is_active,
    )

    db.add(source)
    db.commit()
    db.refresh(source)

    return source


def create_ingestion_request(
    source_system_id,
    idempotency_key="TEST-BATCH-001",
    transaction_id="TEST-TXN-001",
    amount="1500.00",
):
    return PaymentIngestionRequest(
        source_system_id=source_system_id,
        idempotency_key=idempotency_key,
        transactions=[
            {
                "external_transaction_id": transaction_id,
                "amount": Decimal(amount),
                "currency": "INR",
                "transaction_type": "PAYMENT",
                "transaction_timestamp": datetime.fromisoformat(
                    "2026-11-24T10:30:00+05:30"
                ),
                "raw_payload": {
                    "gateway_reference": "GW-REF-001",
                    "payment_method": "UPI",
                    "gateway_status": "SUCCESS",
                },
            }
        ],
    )


def test_successful_payment_ingestion(db):
    source = create_source_system(db)

    request = create_ingestion_request(source.id)

    service = PaymentIngestionService(db)

    result = service.ingest(request)

    assert result.is_replay is False
    assert result.batch.total_records == 1
    assert result.batch.accepted_records == 1
    assert result.batch.duplicate_records == 0
    assert len(result.transactions) == 1
    assert (
        result.transactions[0].external_transaction_id
        == "TEST-TXN-001"
    )


def test_idempotent_replay(db):
    source = create_source_system(db)

    request = create_ingestion_request(source.id)

    service = PaymentIngestionService(db)

    first_result = service.ingest(request)
    second_result = service.ingest(request)

    assert first_result.is_replay is False
    assert second_result.is_replay is True

    assert first_result.batch.id == second_result.batch.id
    assert first_result.batch.idempotency_key == (
        second_result.batch.idempotency_key
    )


def test_idempotency_conflict(db):
    source = create_source_system(db)

    first_request = create_ingestion_request(
        source.id,
        amount="1500.00",
    )

    changed_request = create_ingestion_request(
        source.id,
        amount="2500.00",
    )

    service = PaymentIngestionService(db)

    service.ingest(first_request)

    with pytest.raises(IdempotencyConflictError):
        service.ingest(changed_request)


def test_duplicate_transaction_detection(db):
    source = create_source_system(db)

    service = PaymentIngestionService(db)

    first_request = create_ingestion_request(
        source.id,
        idempotency_key="TEST-BATCH-001",
        transaction_id="DUPLICATE-TXN-001",
    )

    second_request = create_ingestion_request(
        source.id,
        idempotency_key="TEST-BATCH-002",
        transaction_id="DUPLICATE-TXN-001",
    )

    service.ingest(first_request)

    second_result = service.ingest(second_request)

    assert second_result.batch.total_records == 1
    assert second_result.batch.accepted_records == 0
    assert second_result.batch.duplicate_records == 1
    assert len(second_result.transactions) == 0


def test_mixed_new_and_duplicate_transactions(db):
    source = create_source_system(db)

    service = PaymentIngestionService(db)

    first_request = create_ingestion_request(
        source.id,
        idempotency_key="TEST-BATCH-001",
        transaction_id="EXISTING-TXN",
    )

    service.ingest(first_request)

    second_request = PaymentIngestionRequest(
        source_system_id=source.id,
        idempotency_key="TEST-BATCH-002",
        transactions=[
            {
                "external_transaction_id": "EXISTING-TXN",
                "amount": Decimal("1500.00"),
                "currency": "INR",
                "transaction_type": "PAYMENT",
                "transaction_timestamp": datetime.fromisoformat(
                    "2026-11-24T10:30:00+05:30"
                ),
                "raw_payload": {"payment_method": "UPI"},
            },
            {
                "external_transaction_id": "NEW-TXN",
                "amount": Decimal("2500.00"),
                "currency": "INR",
                "transaction_type": "PAYMENT",
                "transaction_timestamp": datetime.fromisoformat(
                    "2026-11-24T10:35:00+05:30"
                ),
                "raw_payload": {"payment_method": "CARD"},
            },
        ],
    )

    result = service.ingest(second_request)

    assert result.batch.total_records == 2
    assert result.batch.accepted_records == 1
    assert result.batch.duplicate_records == 1
    assert len(result.transactions) == 1
    assert (
        result.transactions[0].external_transaction_id == "NEW-TXN"
    )


def test_source_system_not_found(db):
    request = create_ingestion_request(
        uuid4(),
    )

    service = PaymentIngestionService(db)

    with pytest.raises(SourceSystemNotFoundError):
        service.ingest(request)


def test_inactive_source_system_rejected(db):
    source = create_source_system(
        db,
        is_active=False,
    )

    request = create_ingestion_request(source.id)

    service = PaymentIngestionService(db)

    with pytest.raises(SourceSystemInactiveError):
        service.ingest(request)


def test_failed_ingestion_does_not_create_batch(db):
    source = create_source_system(db)

    request = create_ingestion_request(source.id)

    request.idempotency_key = "TEST-ROLLBACK-001"

    service = PaymentIngestionService(db)

    with pytest.raises(SourceSystemNotFoundError):
        invalid_request = create_ingestion_request(uuid4())
        service.ingest(invalid_request)

    # The failed request must not create an ingestion batch.
    from sqlalchemy import select

    from app.models.ingestion_batch import IngestionBatch

    batches = db.scalars(
        select(IngestionBatch).where(
            IngestionBatch.idempotency_key == "TEST-ROLLBACK-001"
        )
    ).all()

    assert len(batches) == 0
