
from uuid import uuid4

from app.modules.ingestion.schemas import PaymentIngestionRequest
from app.modules.ingestion.service import (
    PaymentIngestionService,
    IdempotencyConflictError,
)

from tests.helpers.payload_helpers import build_payload
from tests.helpers.concurrency_helpers import execute_concurrently


def run_ingestion(session_factory, payload):
    """
    Execute ingestion using an independent SQLAlchemy session.

    Each worker gets its own session to simulate concurrent
    requests against PostgreSQL.
    """
    db = session_factory()

    try:
        request = PaymentIngestionRequest.model_validate(payload)
        service = PaymentIngestionService(db)

        return service.ingest(request)

    finally:
        db.close()


def test_concurrent_same_key_same_payload(
    concurrency_session_factory,
    concurrency_source_system_id,
):
    """Two simultaneous requests with identical payloads."""

    payload = build_payload(
        concurrency_source_system_id,
        f"CONCURRENT-{uuid4()}",
    )

    results = execute_concurrently(
        operation=lambda _: run_ingestion(
            concurrency_session_factory,
            payload,
        ),
        workers=2,
    )

    assert len(results) == 2

    assert len({str(result.batch.id) for result in results}) == 1

    assert sum(not result.is_replay for result in results) == 1
    assert sum(result.is_replay for result in results) == 1


def test_concurrent_same_key_same_payload_multiple_workers(
    concurrency_session_factory,
    concurrency_source_system_id,
):
    """Five simultaneous requests with identical payloads."""

    payload = build_payload(
        concurrency_source_system_id,
        f"CONCURRENT-FIVE-{uuid4()}",
    )

    results = execute_concurrently(
        operation=lambda _: run_ingestion(
            concurrency_session_factory,
            payload,
        ),
        workers=5,
    )

    assert len(results) == 5

    assert len({str(result.batch.id) for result in results}) == 1

    assert sum(not result.is_replay for result in results) == 1
    assert sum(result.is_replay for result in results) == 4


def test_concurrent_different_idempotency_keys(
    concurrency_session_factory,
    concurrency_source_system_id,
):
    """Different idempotency keys should create independent batches."""

    payloads = [
        build_payload(
            concurrency_source_system_id,
            f"DIFFERENT-KEY-{uuid4()}",
        )
        for _ in range(2)
    ]

    results = execute_concurrently(
        operation=lambda index: run_ingestion(
            concurrency_session_factory,
            payloads[index],
        ),
        workers=2,
    )

    assert len(results) == 2

    batch_ids = {str(result.batch.id) for result in results}

    assert len(batch_ids) == 2

    assert all(not result.is_replay for result in results)


def test_concurrent_same_transactions_different_batches(
    concurrency_session_factory,
    concurrency_source_system_id,
):
    """
    Two batches ingesting the same transaction simultaneously.

    Expected:
    - Two independent ingestion batches.
    - Only one raw transaction accepted.
    - The other batch records a duplicate.
    """

    transaction_id = f"SHARED-TXN-{uuid4()}"

    payloads = [
        build_payload(
            concurrency_source_system_id,
            f"SHARED-BATCH-{uuid4()}",
            [transaction_id],
        )
        for _ in range(2)
    ]

    results = execute_concurrently(
        operation=lambda index: run_ingestion(
            concurrency_session_factory,
            payloads[index],
        ),
        workers=2,
    )

    assert len(results) == 2

    assert len({str(result.batch.id) for result in results}) == 2

    assert sum(result.batch.accepted_records for result in results) == 1

    assert sum(result.batch.duplicate_records for result in results) == 1


def test_concurrent_partially_overlapping_transactions(
    concurrency_session_factory,
    concurrency_source_system_id,
):
    """
    Two concurrent batches with partially overlapping transactions.

    Batch A: TXN-1, TXN-2
    Batch B: TXN-2, TXN-3

    Expected:
    - Three unique raw transactions.
    - One duplicate transaction.
    - Four total transaction submissions.
    """

    txn_1 = f"TXN-1-{uuid4()}"
    txn_2 = f"TXN-2-{uuid4()}"
    txn_3 = f"TXN-3-{uuid4()}"

    payloads = [
        build_payload(
            concurrency_source_system_id,
            f"OVERLAP-A-{uuid4()}",
            [txn_1, txn_2],
        ),
        build_payload(
            concurrency_source_system_id,
            f"OVERLAP-B-{uuid4()}",
            [txn_2, txn_3],
        ),
    ]

    results = execute_concurrently(
        operation=lambda index: run_ingestion(
            concurrency_session_factory,
            payloads[index],
        ),
        workers=2,
    )

    assert len(results) == 2

    assert sum(result.batch.accepted_records for result in results) == 3

    assert sum(result.batch.duplicate_records for result in results) == 1

    assert sum(result.batch.total_records for result in results) == 4


def test_concurrent_same_key_different_payload(
    concurrency_session_factory,
    concurrency_source_system_id,
):
    """
    Concurrent requests using the same idempotency key
    but different payloads.

    Expected:
    - One request succeeds.
    - One request raises the application's idempotency conflict.
    """

    idempotency_key = f"CONFLICT-{uuid4()}"

    payloads = [
        build_payload(
            concurrency_source_system_id,
            idempotency_key,
            [f"CONFLICT-TXN-{uuid4()}"],
        )
        for _ in range(2)
    ]

    payloads[1]["transactions"][0]["amount"] = "9999.00"

    def safe_operation(index):
        try:
            return run_ingestion(
                concurrency_session_factory,
                payloads[index],
            )
        except Exception as exc:
            return exc

    results = execute_concurrently(
        operation=safe_operation,
        workers=2,
    )

    successes = [
        result
        for result in results
        if not isinstance(result, Exception)
    ]

    failures = [
        result
        for result in results
        if isinstance(result, Exception)
    ]

    assert len(successes) == 1
    assert len(failures) == 1

    assert isinstance(failures[0], IdempotencyConflictError)


def test_high_concurrency_same_key(
    concurrency_session_factory,
    concurrency_source_system_id,
):
    """Stress test with ten simultaneous requests."""

    payload = build_payload(
        concurrency_source_system_id,
        f"HIGH-CONCURRENCY-{uuid4()}",
    )

    results = execute_concurrently(
        operation=lambda _: run_ingestion(
            concurrency_session_factory,
            payload,
        ),
        workers=10,
    )

    assert len(results) == 10

    assert len({str(result.batch.id) for result in results}) == 1

    assert sum(not result.is_replay for result in results) == 1
    assert sum(result.is_replay for result in results) == 9
