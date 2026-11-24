
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.source_systems.schemas import (
    SourceSystemCreate,
    SourceSystemResponse,
    SourceSystemUpdate,
)
from app.modules.source_systems.service import (
    DuplicateSourceSystemCodeError,
    SourceSystemNotFoundError,
    SourceSystemService,
)


router = APIRouter(
    prefix="/api/v1/source-systems",
    tags=["Source Systems"],
)


@router.post(
    "",
    response_model=SourceSystemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_source_system(
    request: SourceSystemCreate,
    db: Session = Depends(get_db),
):
    service = SourceSystemService(db)

    try:
        return service.create(request)

    except DuplicateSourceSystemCodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=list[SourceSystemResponse],
)
def get_source_systems(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    service = SourceSystemService(db)

    return service.get_all(
        offset=offset,
        limit=limit,
        active_only=active_only,
    )


@router.get(
    "/{source_system_id}",
    response_model=SourceSystemResponse,
)
def get_source_system(
    source_system_id: UUID,
    db: Session = Depends(get_db),
):
    service = SourceSystemService(db)

    try:
        return service.get_by_id(source_system_id)

    except SourceSystemNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.put(
    "/{source_system_id}",
    response_model=SourceSystemResponse,
)
def update_source_system(
    source_system_id: UUID,
    request: SourceSystemUpdate,
    db: Session = Depends(get_db),
):
    service = SourceSystemService(db)

    try:
        return service.update(source_system_id, request)

    except SourceSystemNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except DuplicateSourceSystemCodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.patch(
    "/{source_system_id}/deactivate",
    response_model=SourceSystemResponse,
)
def deactivate_source_system(
    source_system_id: UUID,
    db: Session = Depends(get_db),
):
    service = SourceSystemService(db)

    try:
        return service.set_active_status(
            source_system_id,
            is_active=False,
        )

    except SourceSystemNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.patch(
    "/{source_system_id}/activate",
    response_model=SourceSystemResponse,
)
def activate_source_system(
    source_system_id: UUID,
    db: Session = Depends(get_db),
):
    service = SourceSystemService(db)

    try:
        return service.set_active_status(
            source_system_id,
            is_active=True,
        )

    except SourceSystemNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
