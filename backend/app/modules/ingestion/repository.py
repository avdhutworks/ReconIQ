
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.source_system import SourceSystem
from app.models.ingestion_batch import IngestionBatch
from app.models.raw_transaction import RawTransaction


class IngestionRepository:

    def __init__(self, db: Session):
        self.db = db

    # --------------------------------------------------
    # SOURCE SYSTEM
    # --------------------------------------------------

    def get_source_system(
        self,
        source_system_id: UUID,
    ) -> SourceSystem | None:

        statement = select(SourceSystem).where(
            SourceSystem.id == source_system_id
        )

        return self.db.scalar(statement)

    # --------------------------------------------------
    # INGESTION BATCH
    # --------------------------------------------------

    def get_batch_by_idempotency_key(
        self,
        source_system_id: UUID,
        idempotency_key: str,
    ) -> IngestionBatch | None:

        statement = select(IngestionBatch).where(
            IngestionBatch.source_system_id == source_system_id,
            IngestionBatch.idempotency_key == idempotency_key,
        )

        return self.db.scalar(statement)

    def create_batch_if_not_exists(
        self,
        source_system_id: UUID,
        idempotency_key: str,
        request_hash: str,
        total_records: int,
    ) -> IngestionBatch | None:
        """
        Atomically create an ingestion batch.

        Returns:
            IngestionBatch: If this request created the batch.
            None: If the idempotency key already exists.

        PostgreSQL's unique constraint handles concurrent requests.
        """

        statement = (
            insert(IngestionBatch)
            .values(
                source_system_id=source_system_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                total_records=total_records,
                accepted_records=0,
                duplicate_records=0,
                status="COMPLETED",
            )
            .on_conflict_do_nothing(
                constraint="uq_ingestion_batches_source_idempotency"
            )
            .returning(IngestionBatch)
        )

        return self.db.scalars(statement).one_or_none()

    def get_batch_by_id(
        self,
        batch_id: UUID,
    ) -> IngestionBatch | None:

        statement = select(IngestionBatch).where(
            IngestionBatch.id == batch_id
        )

        return self.db.scalar(statement)

    def update_batch_counts(
        self,
        batch: IngestionBatch,
        accepted_records: int,
        duplicate_records: int,
    ) -> IngestionBatch:

        batch.accepted_records = accepted_records
        batch.duplicate_records = duplicate_records

        self.db.flush()

        return batch

    def get_batches(
        self,
        source_system_id: UUID | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[IngestionBatch], int]:

        statement = select(IngestionBatch)

        count_statement = select(
            func.count()
        ).select_from(IngestionBatch)

        if source_system_id is not None:
            statement = statement.where(
                IngestionBatch.source_system_id == source_system_id
            )

            count_statement = count_statement.where(
                IngestionBatch.source_system_id == source_system_id
            )

        statement = (
            statement
            .order_by(IngestionBatch.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        batches = list(self.db.scalars(statement).all())
        total = self.db.scalar(count_statement) or 0

        return batches, total

    # --------------------------------------------------
    # RAW TRANSACTIONS
    # --------------------------------------------------

    def insert_raw_transactions(
        self,
        batch_id: UUID,
        source_system_id: UUID,
        transactions: list[dict[str, Any]],
    ) -> int:

        if not transactions:
            return 0

        records = [
            {
                "batch_id": batch_id,
                "source_system_id": source_system_id,
                "external_transaction_id": transaction[
                    "external_transaction_id"
                ],
                "amount": transaction["amount"],
                "currency": transaction["currency"],
                "transaction_type": transaction["transaction_type"],
                "transaction_timestamp": transaction[
                    "transaction_timestamp"
                ],
                "raw_payload": transaction["raw_payload"],
            }
            for transaction in transactions
        ]

        statement = (
            insert(RawTransaction)
            .values(records)
            .on_conflict_do_nothing(
                constraint="uq_raw_transactions_source_external_id"
            )
            .returning(RawTransaction.id)
        )

        inserted_ids = self.db.scalars(statement).all()

        return len(inserted_ids)

    def get_transactions_by_batch(
        self,
        batch_id: UUID,
    ) -> list[RawTransaction]:

        statement = (
            select(RawTransaction)
            .where(RawTransaction.batch_id == batch_id)
            .order_by(RawTransaction.received_at.asc())
        )

        return list(self.db.scalars(statement).all())

    def get_raw_transaction_by_id(
        self,
        transaction_id: UUID,
    ) -> RawTransaction | None:

        statement = select(RawTransaction).where(
            RawTransaction.id == transaction_id
        )

        return self.db.scalar(statement)

    def get_raw_transactions(
        self,
        source_system_id: UUID | None = None,
        batch_id: UUID | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[RawTransaction], int]:

        statement = select(RawTransaction)

        count_statement = select(
            func.count()
        ).select_from(RawTransaction)

        if source_system_id is not None:
            statement = statement.where(
                RawTransaction.source_system_id == source_system_id
            )

            count_statement = count_statement.where(
                RawTransaction.source_system_id == source_system_id
            )

        if batch_id is not None:
            statement = statement.where(
                RawTransaction.batch_id == batch_id
            )

            count_statement = count_statement.where(
                RawTransaction.batch_id == batch_id
            )

        statement = (
            statement
            .order_by(RawTransaction.received_at.desc())
            .offset(offset)
            .limit(limit)
        )

        transactions = list(self.db.scalars(statement).all())
        total = self.db.scalar(count_statement) or 0

        return transactions, total
