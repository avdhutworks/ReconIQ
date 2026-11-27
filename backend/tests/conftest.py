
import os

import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker
from sqlalchemy import delete

from app.models.source_system import SourceSystem
from app.models.ingestion_batch import IngestionBatch
from app.models.raw_transaction import RawTransaction
from app.core.database import Base, get_db
from app.main import app as fastapi_app

# Import all models so that SQLAlchemy metadata knows every table.
import app.models  # noqa: F401


TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://reconiq:local_dev_password"
    "@localhost:5432/reconiq_test",
)

# Safety check: never allow automated tests to use the development DB.
database_name = make_url(TEST_DATABASE_URL).database

if database_name != "reconiq_test":
    raise RuntimeError(
        "Tests must use the dedicated 'reconiq_test' database. "
        f"Current database: {database_name}"
    )


@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(
        TEST_DATABASE_URL,
        pool_pre_ping=True,
    )

    Base.metadata.create_all(bind=engine)

    yield engine

    engine.dispose()


@pytest.fixture(scope="session")
def concurrency_session_factory(test_engine):
    return sessionmaker(
        bind=test_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


@pytest.fixture
def concurrency_source_system_id(concurrency_session_factory):
    """
    Create a committed source system visible to independent
    database sessions used by concurrency tests.
    """
    db = concurrency_session_factory()

    source_system = SourceSystem(
        code=f"CONCURRENCY_{uuid4().hex[:12]}",
        name="Concurrency Test Source",
        description="Source system for ingestion concurrency tests",
        is_active=True,
    )

    try:
        db.add(source_system)
        db.commit()
        db.refresh(source_system)

        source_system_id = source_system.id

        yield str(source_system_id)

    finally:
        # Delete dependent records before deleting the source.
        db.query(RawTransaction).filter(
            RawTransaction.source_system_id == source_system_id
        ).delete(synchronize_session=False)

        db.query(IngestionBatch).filter(
            IngestionBatch.source_system_id == source_system_id
        ).delete(synchronize_session=False)

        db.query(SourceSystem).filter(
            SourceSystem.id == source_system_id
        ).delete(synchronize_session=False)

        db.commit()
        db.close()



@pytest.fixture
def source_system_id(client):
    response = client.post(
        "/api/v1/source-systems",
        json={
            "code": f"TEST_{uuid4().hex[:8]}",
            "name": "Test Payment Gateway",
            "description": "Automated test source system",
        },
    )

    assert response.status_code == 201

    return response.json()["id"]

@pytest.fixture()
def db(test_engine):
    """
    Give each test an isolated transaction.

    Service methods may call commit(). SQLAlchemy's
    create_savepoint mode keeps those commits inside
    the outer test transaction.
    """
    connection = test_engine.connect()
    outer_transaction = connection.begin()

    # Clear only the dedicated test database.
    for table in reversed(Base.metadata.sorted_tables):
        connection.execute(table.delete())

    session = Session(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    yield session

    session.close()
    outer_transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db):
    """
    FastAPI TestClient using the isolated test session.
    """

    def override_get_db():
        yield db

    fastapi_app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(fastapi_app) as test_client:
            yield test_client
    finally:
        fastapi_app.dependency_overrides.clear()

@pytest.fixture
def concurrency_source_system_id(concurrency_session_factory):
    """
    Create a committed source system that is visible
    to all independent database sessions used by
    concurrency workers.
    """

    with concurrency_session_factory() as db:
        source_system = SourceSystem(
            code=f"CONCURRENCY_{uuid4().hex[:12]}",
            name="Concurrency Test Source",
            description="Source system for concurrency tests",
            is_active=True,
        )

        db.add(source_system)
        db.commit()
        db.refresh(source_system)

        source_system_id = source_system.id

    yield str(source_system_id)

    # Clean up records created by the concurrency test.
    with concurrency_session_factory() as db:
        db.execute(
            delete(RawTransaction).where(
                RawTransaction.source_system_id == source_system_id
            )
        )

        db.execute(
            delete(IngestionBatch).where(
                IngestionBatch.source_system_id == source_system_id
            )
        )

        db.execute(
            delete(SourceSystem).where(
                SourceSystem.id == source_system_id
            )
        )

        db.commit()        
