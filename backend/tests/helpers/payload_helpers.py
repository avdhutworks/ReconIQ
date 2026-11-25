from datetime import datetime, timezone
from uuid import uuid4


def build_payload(source_system_id, idempotency_key, transaction_ids=None):
    if transaction_ids is None:
        transaction_ids = [f"TXN-{uuid4()}"]

    transactions = [
        {
            "external_transaction_id": transaction_id,
            "amount": "1500.00",
            "currency": "INR",
            "transaction_type": "PAYMENT",
            "transaction_timestamp": datetime.now(timezone.utc).isoformat(),
            "raw_payload": {
                "reference": "RECONIQ-CONCURRENCY",
                "channel": "UPI",
            },
        }
        for transaction_id in transaction_ids
    ]

    return {
        "source_system_id": str(source_system_id),
        "idempotency_key": idempotency_key,
        "transactions": transactions,
    }