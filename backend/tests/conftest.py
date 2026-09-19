"""
Pytest configuration and fixtures.
"""

import os
from typing import Generator
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.main import create_app
from app.db.session import get_db


# Use in-memory SQLite database for testing
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def db_engine():
    """Create a test database engine."""
    engine = create_engine(
        SQLALCHEMY_TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db(db_engine) -> Generator[Session, None, None]:
    """Create a test database session."""
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=db_engine,
    )
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="function")
def client(db: Session):
    """Create a test client with test database."""
    def override_get_db():
        yield db

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture
def architecture_data():
    """Sample architecture data for tests."""
    return {
        "name": "Test Architecture",
        "description": "A test architecture",
        "provider": "azure",
    }


@pytest.fixture
def version_data():
    """Sample version data for tests."""
    return {
        "version_number": "1.0",
        "status": "draft",
        "created_by": "test_user",
    }


@pytest.fixture
def resource_group_data():
    """Sample resource group data for tests."""
    return {
        "resource_key": "rg-test",
        "resource_type": "microsoft.resources/resourcegroups",
        "name": "test-rg",
        "location": "eastus",
        "properties": {"environment": "test"},
        "tags": {"project": "architect-companion"},
    }


@pytest.fixture
def vnet_data():
    """Sample virtual network data for tests."""
    return {
        "resource_key": "vnet-test",
        "resource_type": "microsoft.network/virtualnetworks",
        "name": "test-vnet",
        "location": "eastus",
        "properties": {"addressSpace": {"addressPrefixes": ["10.0.0.0/16"]}},
    }


@pytest.fixture
def subnet_data():
    """Sample subnet data for tests."""
    return {
        "resource_key": "subnet-test",
        "resource_type": "microsoft.network/virtualnetworks/subnets",
        "name": "test-subnet",
        "location": "eastus",
        "properties": {"addressPrefix": "10.0.1.0/24"},
    }
