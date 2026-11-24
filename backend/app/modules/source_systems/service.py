
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.source_system import SourceSystem
from app.modules.source_systems.repository import SourceSystemRepository
from app.modules.source_systems.schemas import (
    SourceSystemCreate,
    SourceSystemUpdate,
)


class SourceSystemNotFoundError(Exception):
    pass


class DuplicateSourceSystemCodeError(Exception):
    pass


class SourceSystemService:

    def __init__(self, db: Session):
        self.db = db
        self.repository = SourceSystemRepository(db)

    def create(
        self,
        request: SourceSystemCreate,
    ) -> SourceSystem:

        existing = self.repository.get_by_code(request.code)

        if existing:
            raise DuplicateSourceSystemCodeError(
                f"Source system code '{request.code}' already exists"
            )

        source_system = SourceSystem(
            code=request.code,
            name=request.name,
            description=request.description,
        )

        try:
            self.repository.create(source_system)
            self.db.commit()
            self.db.refresh(source_system)

            return source_system

        except IntegrityError as exc:
            self.db.rollback()
            raise DuplicateSourceSystemCodeError(
                f"Source system code '{request.code}' already exists"
            ) from exc

        except Exception:
            self.db.rollback()
            raise

    def get_by_id(self, source_system_id: UUID) -> SourceSystem:

        source_system = self.repository.get_by_id(source_system_id)

        if not source_system:
            raise SourceSystemNotFoundError(
                f"Source system '{source_system_id}' not found"
            )

        return source_system

    def get_all(
        self,
        offset: int = 0,
        limit: int = 20,
        active_only: bool = False,
    ) -> list[SourceSystem]:

        return self.repository.get_all(
            offset=offset,
            limit=limit,
            active_only=active_only,
        )

    def update(
        self,
        source_system_id: UUID,
        request: SourceSystemUpdate,
    ) -> SourceSystem:

        source_system = self.get_by_id(source_system_id)

        existing = self.repository.get_by_code(request.code)

        if existing and existing.id != source_system_id:
            raise DuplicateSourceSystemCodeError(
                f"Source system code '{request.code}' already exists"
            )

        source_system.code = request.code
        source_system.name = request.name
        source_system.description = request.description

        try:
            self.db.commit()
            self.db.refresh(source_system)

            return source_system

        except IntegrityError as exc:
            self.db.rollback()
            raise DuplicateSourceSystemCodeError(
                f"Source system code '{request.code}' already exists"
            ) from exc

        except Exception:
            self.db.rollback()
            raise

    def set_active_status(
        self,
        source_system_id: UUID,
        is_active: bool,
    ) -> SourceSystem:

        source_system = self.get_by_id(source_system_id)

        source_system.is_active = is_active

        try:
            self.db.commit()
            self.db.refresh(source_system)

            return source_system

        except Exception:
            self.db.rollback()
            raise