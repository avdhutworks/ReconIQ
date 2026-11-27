
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.ingestion.schemas import (
    PaymentIngestionRequest,
)


def test_valid_ingestion_request():
    request = PaymentIngestionRequest(
        source_system_id=uuid4(),
        idempotency_key="BATCH-001",
        transactions=[
            {
                "external_transaction_id": "TXN-001",
                "amount": "1250.500000",
                "currency": "inr",
                "transaction_type": "PAYMENT",
                "transaction_timestamp": "2026-11-24T10:30:00+05:30",
                "raw_payload": {
                    "gateway_reference": "GW-1001"
                },
            }
        ],
    )

    assert request.transactions[0].amount == Decimal("1250.500000")
    assert request.transactions[0].currency == "INR"
    assert request.transactions[0].external_transaction_id == "TXN-001"


def test_reject_invalid_transaction_type():
    with pytest.raises(ValidationError):
        PaymentIngestionRequest(
            source_system_id=uuid4(),
            idempotency_key="BATCH-002",
            transactions=[
                {
                    "external_transaction_id": "TXN-002",
                    "amount": "100",
                    "currency": "INR",
                    "transaction_type": "UNKNOWN",
                    "transaction_timestamp": "2026-11-24T10:30:00+05:30",
                    "raw_payload": {},
                }
            ],
        )


def test_reject_timestamp_without_timezone():
    with pytest.raises(ValidationError):
        PaymentIngestionRequest(
            source_system_id=uuid4(),
            idempotency_key="BATCH-003",
            transactions=[
                {
                    "external_transaction_id": "TXN-003",
                    "amount": "100",
                    "currency": "INR",
                    "transaction_type": "PAYMENT",
                    "transaction_timestamp": "2026-11-24T10:30:00",
                    "raw_payload": {},
                }
            ],
        )
