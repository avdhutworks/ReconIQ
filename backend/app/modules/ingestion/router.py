
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.ingestion.repository import IngestionRepository
from app.modules.ingestion.schemas import (
    IngestionBatchDetailResponse,
    IngestionBatchResponse,
    PaginatedIngestionBatchResponse,
    PaginatedRawTransactionResponse,
    RawTransactionResponse,
    PaymentIngestionRequest,
)
from app.modules.ingestion.service import (
    PaymentIngestionService,
    SourceSystemNotFoundError,
    SourceSystemInactiveError,
    IdempotencyConflictError,
)


router = APIRouter(
    prefix="/api/v1",
    tags=["Payment Ingestion"],
)


# ==========================================================
# PAYMENT INGESTION
# ==========================================================

@router.post(
    "/ingestion/batches",
    response_model=IngestionBatchDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit payment transactions",
    description=(
        "Ingest a batch of payment transactions from a registered "
        "source system. Supports idempotency and duplicate detection."
    ),
)
def create_ingestion_batch(
    request: PaymentIngestionRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    service = PaymentIngestionService(db)

    try:
        result = service.ingest(request)

        # A replay is an existing batch, not a newly created resource.
        if result.is_replay:
            response.status_code = status.HTTP_200_OK
            response.headers["X-Idempotent-Replay"] = "true"
        else:
            response.headers["X-Idempotent-Replay"] = "false"

        return IngestionBatchDetailResponse(
            id=result.batch.id,
            source_system_id=result.batch.source_system_id,
            idempotency_key=result.batch.idempotency_key,
            status=result.batch.status,
            total_records=result.batch.total_records,
            accepted_records=result.batch.accepted_records,
            duplicate_records=result.batch.duplicate_records,
            created_at=result.batch.created_at,
            transactions=result.transactions,
        )

    except SourceSystemNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except SourceSystemInactiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except IdempotencyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


# ==========================================================
# INGESTION BATCH QUERIES
# ==========================================================

@router.get(
    "/ingestion/batches",
    response_model=PaginatedIngestionBatchResponse,
    summary="List ingestion batches",
)
def get_ingestion_batches(
    source_system_id: UUID | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    repository = IngestionRepository(db)

    batches, total = repository.get_batches(
        source_system_id=source_system_id,
        offset=offset,
        limit=limit,
    )

    return PaginatedIngestionBatchResponse(
        items=batches,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/ingestion/batches/{batch_id}",
    response_model=IngestionBatchDetailResponse,
    summary="Get ingestion batch details",
)
def get_ingestion_batch(
    batch_id: UUID,
    db: Session = Depends(get_db),
):
    repository = IngestionRepository(db)

    batch = repository.get_batch_by_id(batch_id)

    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion batch not found.",
        )

    transactions = repository.get_transactions_by_batch(
        batch_id=batch.id
    )

    return IngestionBatchDetailResponse(
        id=batch.id,
        source_system_id=batch.source_system_id,
        idempotency_key=batch.idempotency_key,
        status=batch.status,
        total_records=batch.total_records,
        accepted_records=batch.accepted_records,
        duplicate_records=batch.duplicate_records,
        created_at=batch.created_at,
        transactions=transactions,
    )


# ==========================================================
# RAW TRANSACTION QUERIES
# ==========================================================

@router.get(
    "/raw-transactions",
    response_model=PaginatedRawTransactionResponse,
    summary="List raw transactions",
)
def get_raw_transactions(
    source_system_id: UUID | None = Query(default=None),
    batch_id: UUID | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    repository = IngestionRepository(db)

    transactions, total = repository.get_raw_transactions(
        source_system_id=source_system_id,
        batch_id=batch_id,
        offset=offset,
        limit=limit,
    )

    return PaginatedRawTransactionResponse(
        items=transactions,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/raw-transactions/{transaction_id}",
    response_model=RawTransactionResponse,
    summary="Get raw transaction details",
)
def get_raw_transaction(
    transaction_id: UUID,
    db: Session = Depends(get_db),
):
    repository = IngestionRepository(db)

    transaction = repository.get_raw_transaction_by_id(
        transaction_id=transaction_id
    )

    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Raw transaction not found.",
        )

    return transaction
