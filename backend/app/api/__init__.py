
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db


router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


@router.get("")
def application_health():
    return {
        "status": "UP",
        "service": "ReconIQ",
    }


@router.get("/db")
def database_health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))

        return {
            "status": "UP",
            "database": "PostgreSQL",
            "connection": "SUCCESS",
        }

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed",
        ) from exc