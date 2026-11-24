
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.source_system import SourceSystem


class SourceSystemRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, source_system: SourceSystem) -> SourceSystem:
        self.db.add(source_system)
        self.db.flush()
        self.db.refresh(source_system)

        return source_system

    def get_by_id(self, source_system_id: UUID) -> SourceSystem | None:
        statement = select(SourceSystem).where(
            SourceSystem.id == source_system_id
        )

        return self.db.scalar(statement)

    def get_by_code(self, code: str) -> SourceSystem | None:
        statement = select(SourceSystem).where(
            SourceSystem.code == code
        )

        return self.db.scalar(statement)

    def get_all(
        self,
        offset: int = 0,
        limit: int = 20,
        active_only: bool = False,
    ) -> list[SourceSystem]:

        statement = select(SourceSystem)

        if active_only:
            statement = statement.where(
                SourceSystem.is_active.is_(True)
            )

        statement = (
            statement
            .order_by(SourceSystem.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        return list(self.db.scalars(statement).all())