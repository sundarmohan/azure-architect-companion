"""
Tests for architecture and version services.
"""

from uuid import uuid4
import pytest
from sqlalchemy.orm import Session

from app.services import ArchitectureService, ArchitectureVersionService
from app.schemas import ArchitectureCreate, ArchitectureUpdate, ArchitectureVersionCreate
from app.models import Architecture, ArchitectureVersion


class TestArchitectureService:
    """Tests for ArchitectureService."""

    def test_create_architecture(self, db: Session, architecture_data):
        """Test creating an architecture."""
        schema = ArchitectureCreate(**architecture_data)
        architecture = ArchitectureService.create(db, schema)

        assert architecture is not None
        assert architecture.id is not None
        assert architecture.name == architecture_data["name"]
        assert architecture.description == architecture_data["description"]
        assert architecture.provider == architecture_data["provider"]
        assert architecture.created_at is not None
        assert architecture.updated_at is not None

    def test_get_architecture(self, db: Session, architecture_data):
        """Test getting an architecture by ID."""
        schema = ArchitectureCreate(**architecture_data)
        created = ArchitectureService.create(db, schema)

        retrieved = ArchitectureService.get(db, created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == created.name

    def test_get_nonexistent_architecture(self, db: Session):
        """Test getting a nonexistent architecture."""
        result = ArchitectureService.get(db, uuid4())
        assert result is None

    def test_list_all_architectures(self, db: Session, architecture_data):
        """Test listing all architectures."""
        # Create multiple architectures
        for i in range(3):
            data = {**architecture_data, "name": f"{architecture_data['name']}-{i}"}
            schema = ArchitectureCreate(**data)
            ArchitectureService.create(db, schema)

        architectures = ArchitectureService.list_all(db)
        assert len(architectures) == 3

    def test_update_architecture(self, db: Session, architecture_data):
        """Test updating an architecture."""
        schema = ArchitectureCreate(**architecture_data)
        architecture = ArchitectureService.create(db, schema)

        update_data = ArchitectureUpdate(name="Updated Name")
        updated = ArchitectureService.update(db, architecture.id, update_data)

        assert updated is not None
        assert updated.name == "Updated Name"
        assert updated.description == architecture.description

    def test_delete_architecture(self, db: Session, architecture_data):
        """Test deleting an architecture."""
        schema = ArchitectureCreate(**architecture_data)
        architecture = ArchitectureService.create(db, schema)
        architecture_id = architecture.id

        result = ArchitectureService.delete(db, architecture_id)
        assert result is True

        # Verify it's deleted
        retrieved = ArchitectureService.get(db, architecture_id)
        assert retrieved is None

    def test_delete_nonexistent_architecture(self, db: Session):
        """Test deleting a nonexistent architecture."""
        result = ArchitectureService.delete(db, uuid4())
        assert result is False


class TestArchitectureVersionService:
    """Tests for ArchitectureVersionService."""

    def test_create_version(self, db: Session, architecture_data, version_data):
        """Test creating an architecture version."""
        arch_schema = ArchitectureCreate(**architecture_data)
        architecture = ArchitectureService.create(db, arch_schema)

        version_schema = ArchitectureVersionCreate(**version_data)
        version = ArchitectureVersionService.create(db, architecture.id, version_schema)

        assert version is not None
        assert version.id is not None
        assert version.architecture_id == architecture.id
        assert version.version_number == version_data["version_number"]
        assert version.status == version_data["status"]
        assert version.created_by == version_data["created_by"]

    def test_create_version_for_nonexistent_architecture(self, db: Session, version_data):
        """Test creating a version for a nonexistent architecture."""
        version_schema = ArchitectureVersionCreate(**version_data)
        result = ArchitectureVersionService.create(db, uuid4(), version_schema)
        assert result is None

    def test_get_version(self, db: Session, architecture_data, version_data):
        """Test getting a version by ID."""
        arch_schema = ArchitectureCreate(**architecture_data)
        architecture = ArchitectureService.create(db, arch_schema)

        version_schema = ArchitectureVersionCreate(**version_data)
        created_version = ArchitectureVersionService.create(db, architecture.id, version_schema)

        retrieved = ArchitectureVersionService.get(db, created_version.id)
        assert retrieved is not None
        assert retrieved.id == created_version.id

    def test_list_versions(self, db: Session, architecture_data, version_data):
        """Test listing versions of an architecture."""
        arch_schema = ArchitectureCreate(**architecture_data)
        architecture = ArchitectureService.create(db, arch_schema)

        # Create multiple versions
        for i in range(3):
            data = {**version_data, "version_number": f"1.{i}"}
            schema = ArchitectureVersionCreate(**data)
            ArchitectureVersionService.create(db, architecture.id, schema)

        versions = ArchitectureVersionService.list_by_architecture(db, architecture.id)
        assert len(versions) == 3

    def test_multiple_architecture_versions(self, db: Session, architecture_data, version_data):
        """Test that an architecture can have multiple versions."""
        arch_schema = ArchitectureCreate(**architecture_data)
        architecture = ArchitectureService.create(db, arch_schema)

        # Create V1
        v1_data = {**version_data, "version_number": "1.0"}
        v1_schema = ArchitectureVersionCreate(**v1_data)
        v1 = ArchitectureVersionService.create(db, architecture.id, v1_schema)

        # Create V2
        v2_data = {**version_data, "version_number": "2.0"}
        v2_schema = ArchitectureVersionCreate(**v2_data)
        v2 = ArchitectureVersionService.create(db, architecture.id, v2_schema)

        # Create V3
        v3_data = {**version_data, "version_number": "3.0"}
        v3_schema = ArchitectureVersionCreate(**v3_data)
        v3 = ArchitectureVersionService.create(db, architecture.id, v3_schema)

        versions = ArchitectureVersionService.list_by_architecture(db, architecture.id)
        assert len(versions) == 3
        assert v1.id in [v.id for v in versions]
        assert v2.id in [v.id for v in versions]
        assert v3.id in [v.id for v in versions]
