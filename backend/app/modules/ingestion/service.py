
import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.ingestion_batch import IngestionBatch
from app.models.raw_transaction import RawTransaction
from app.modules.ingestion.repository import IngestionRepository
from app.modules.ingestion.schemas import PaymentIngestionRequest


# ==========================================================
# BUSINESS EXCEPTIONS
# ==========================================================

class SourceSystemNotFoundError(Exception):
    """Raised when the requested source system does not exist."""


class SourceSystemInactiveError(Exception):
    """Raised when an inactive source system submits new data."""


class IdempotencyConflictError(Exception):
    """Raised when an idempotency key is reused with a different payload."""


# ==========================================================
# SERVICE RESULT
# ==========================================================

@dataclass
class IngestionResult:
    batch: IngestionBatch
    transactions: list[RawTransaction]
    is_replay: bool


# ==========================================================
# PAYMENT INGESTION SERVICE
# ==========================================================

class PaymentIngestionService:

    def __init__(self, db: Session):
        self.db = db
        self.repository = IngestionRepository(db)

    # ------------------------------------------------------
    # REQUEST HASHING
    # ------------------------------------------------------

    @staticmethod
    def generate_request_hash(
        request: PaymentIngestionRequest,
    ) -> str:
        """
        Generate a deterministic SHA-256 hash of the
        complete ingestion request.
        """

        request_data = request.model_dump(mode="json")

        canonical_payload = json.dumps(
            request_data,
            sort_keys=True,
            separators=(",", ":"),
        )

        return hashlib.sha256(
            canonical_payload.encode("utf-8")
        ).hexdigest()

    # ------------------------------------------------------
    # IDEMPOTENCY CHECK
    # ------------------------------------------------------

    def check_existing_batch(
        self,
        source_system_id: UUID,
        idempotency_key: str,
        request_hash: str,
    ) -> IngestionResult | None:
        """
        Check whether an ingestion batch already exists.

        Same key + same payload:
            Return the existing batch.

        Same key + different payload:
            Raise IdempotencyConflictError.
        """

        existing_batch = (
            self.repository.get_batch_by_idempotency_key(
                source_system_id=source_system_id,
                idempotency_key=idempotency_key,
            )
        )

        if existing_batch is None:
            return None

        if existing_batch.request_hash != request_hash:
            raise IdempotencyConflictError(
                "Idempotency key already exists with a different payload."
            )

        transactions = (
            self.repository.get_transactions_by_batch(
                batch_id=existing_batch.id
            )
        )

        return IngestionResult(
            batch=existing_batch,
            transactions=transactions,
            is_replay=True,
        )

    # ------------------------------------------------------
    # MAIN INGESTION WORKFLOW
    # ------------------------------------------------------

    def ingest(
        self,
        request: PaymentIngestionRequest,
    ) -> IngestionResult:
        """
        Execute the complete payment ingestion workflow.

        Batch creation and raw transaction insertion are
        committed atomically.

        Concurrent requests using the same idempotency key
        are handled through PostgreSQL's atomic insert.
        """

        try:
            # 1. Validate source system
            source_system = self.repository.get_source_system(
                source_system_id=request.source_system_id
            )

            if source_system is None:
                raise SourceSystemNotFoundError(
                    "Source system does not exist."
                )

            # 2. Generate request hash
            request_hash = self.generate_request_hash(request)

            # 3. Handle an already committed request
            existing_result = self.check_existing_batch(
                source_system_id=request.source_system_id,
                idempotency_key=request.idempotency_key,
                request_hash=request_hash,
            )

            if existing_result is not None:
                return existing_result

            # 4. Validate source system status
            if not source_system.is_active:
                raise SourceSystemInactiveError(
                    "Source system is inactive."
                )

            # 5. Atomically create the ingestion batch
            batch = self.repository.create_batch_if_not_exists(
                source_system_id=request.source_system_id,
                idempotency_key=request.idempotency_key,
                request_hash=request_hash,
                total_records=len(request.transactions),
            )

            # 6. Another concurrent request may have created
            # the same batch after our initial existence check.
            if batch is None:

                existing_result = self.check_existing_batch(
                    source_system_id=request.source_system_id,
                    idempotency_key=request.idempotency_key,
                    request_hash=request_hash,
                )

                if existing_result is not None:
                    return existing_result

                # Under PostgreSQL READ COMMITTED isolation,
                # the conflicting committed batch should be visible.
                raise RuntimeError(
                    "Batch creation conflicted, but the existing "
                    "batch could not be retrieved."
                )

            # 7. Convert Pydantic models into dictionaries
            transaction_records = [
                transaction.model_dump()
                for transaction in request.transactions
            ]

            # 8. Insert raw transactions
            accepted_records = (
                self.repository.insert_raw_transactions(
                    batch_id=batch.id,
                    source_system_id=request.source_system_id,
                    transactions=transaction_records,
                )
            )

            # 9. Calculate duplicate count
            duplicate_records = (
                len(request.transactions) - accepted_records
            )

            # 10. Update batch counters
            self.repository.update_batch_counts(
                batch=batch,
                accepted_records=accepted_records,
                duplicate_records=duplicate_records,
            )

            # 11. Commit batch and transactions atomically
            self.db.commit()

            # 12. Refresh batch from database
            self.db.refresh(batch)

            # 13. Retrieve transactions belonging to this batch
            transactions = (
                self.repository.get_transactions_by_batch(
                    batch_id=batch.id
                )
            )

            return IngestionResult(
                batch=batch,
                transactions=transactions,
                is_replay=False,
            )

        except Exception:
            self.db.rollback()
            raise
