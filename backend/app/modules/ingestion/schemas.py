
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


TransactionType = Literal[
    "PAYMENT",
    "REFUND",
    "REVERSAL",
    "FEE",
]


class PaymentTransactionInput(BaseModel):
    external_transaction_id: str = Field(
        min_length=1,
        max_length=100,
    )

    amount: Decimal = Field(
        max_digits=20,
        decimal_places=6,
    )

    currency: str = Field(
        min_length=3,
        max_length=3,
    )

    transaction_type: TransactionType

    transaction_timestamp: datetime

    raw_payload: dict[str, Any]

    @field_validator("external_transaction_id", mode="before")
    @classmethod
    def normalize_transaction_id(cls, value):
        if isinstance(value, str):
            value = value.strip()
        return value

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value):
        if isinstance(value, str):
            value = value.strip().upper()
        return value

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal):
        if not value.is_finite():
            raise ValueError("Amount must be a finite decimal value")
        return value

    @field_validator("transaction_timestamp")
    @classmethod
    def validate_timestamp(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "Transaction timestamp must include a timezone"
            )
        return value


class PaymentIngestionRequest(BaseModel):
    source_system_id: UUID

    idempotency_key: str = Field(
        min_length=1,
        max_length=100,
    )

    transactions: list[PaymentTransactionInput] = Field(
        min_length=1,
        max_length=1000,
    )

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def normalize_idempotency_key(cls, value):
        if isinstance(value, str):
            value = value.strip()
        return value


class IngestionBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_system_id: UUID
    idempotency_key: str
    status: str
    total_records: int
    accepted_records: int
    duplicate_records: int
    created_at: datetime


class RawTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    batch_id: UUID
    source_system_id: UUID
    external_transaction_id: str
    amount: Decimal
    currency: str
    transaction_type: str
    transaction_timestamp: datetime
    raw_payload: dict[str, Any]
    received_at: datetime


class IngestionBatchDetailResponse(IngestionBatchResponse):
    transactions: list[RawTransactionResponse]


class PaginatedIngestionBatchResponse(BaseModel):
    items: list[IngestionBatchResponse]
    total: int
    limit: int
    offset: int


class PaginatedRawTransactionResponse(BaseModel):
    items: list[RawTransactionResponse]
    total: int
    limit: int
    offset: int