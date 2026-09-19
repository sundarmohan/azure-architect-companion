"""
Tests for API endpoints.
"""

from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check(self, client: TestClient):
        """Test the health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestArchitectureEndpoints:
    """Tests for architecture API endpoints."""

    def test_create_architecture(self, client: TestClient, architecture_data):
        """Test creating an architecture via API."""
        response = client.post("/architectures", json=architecture_data)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == architecture_data["name"]
        assert data["provider"] == architecture_data["provider"]
        assert "id" in data
        assert "created_at" in data

    def test_get_architecture(self, client: TestClient, architecture_data):
        """Test getting an architecture via API."""
        # Create architecture
        create_response = client.post("/architectures", json=architecture_data)
        architecture_id = create_response.json()["id"]

        # Get architecture
        get_response = client.get(f"/architectures/{architecture_id}")
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["id"] == architecture_id
        assert data["name"] == architecture_data["name"]

    def test_get_nonexistent_architecture(self, client: TestClient):
        """Test getting a nonexistent architecture."""
        response = client.get(f"/architectures/{uuid4()}")
        assert response.status_code == 404

    def test_list_architectures(self, client: TestClient, architecture_data):
        """Test listing architectures via API."""
        # Create multiple architectures
        for i in range(3):
            data = {**architecture_data, "name": f"{architecture_data['name']}-{i}"}
            client.post("/architectures", json=data)

        response = client.get("/architectures")
        assert response.status_code == 200
        architectures = response.json()
        assert len(architectures) >= 3

    def test_update_architecture(self, client: TestClient, architecture_data):
        """Test updating an architecture via API."""
        # Create architecture
        create_response = client.post("/architectures", json=architecture_data)
        architecture_id = create_response.json()["id"]

        # Update architecture
        update_data = {"name": "Updated Name"}
        update_response = client.put(f"/architectures/{architecture_id}", json=update_data)
        assert update_response.status_code == 200
        data = update_response.json()
        assert data["name"] == "Updated Name"

    def test_delete_architecture(self, client: TestClient, architecture_data):
        """Test deleting an architecture via API."""
        # Create architecture
        create_response = client.post("/architectures", json=architecture_data)
        architecture_id = create_response.json()["id"]

        # Delete architecture
        delete_response = client.delete(f"/architectures/{architecture_id}")
        assert delete_response.status_code == 204

        # Verify it's deleted
        get_response = client.get(f"/architectures/{architecture_id}")
        assert get_response.status_code == 404


class TestVersionEndpoints:
    """Tests for architecture version endpoints."""

    def test_create_version(self, client: TestClient, architecture_data, version_data):
        """Test creating a version via API."""
        # Create architecture
        arch_response = client.post("/architectures", json=architecture_data)
        architecture_id = arch_response.json()["id"]

        # Create version
        version_response = client.post(
            f"/architectures/{architecture_id}/versions",
            json=version_data
        )
        assert version_response.status_code == 201
        data = version_response.json()
        assert data["version_number"] == version_data["version_number"]
        assert data["architecture_id"] == architecture_id

    def test_get_version(self, client: TestClient, architecture_data, version_data):
        """Test getting a version via API."""
        # Create architecture and version
        arch_response = client.post("/architectures", json=architecture_data)
        architecture_id = arch_response.json()["id"]

        version_response = client.post(
            f"/architectures/{architecture_id}/versions",
            json=version_data
        )
        version_id = version_response.json()["id"]

        # Get version
        get_response = client.get(f"/architectures/{architecture_id}/versions/{version_id}")
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["id"] == version_id

    def test_list_versions(self, client: TestClient, architecture_data, version_data):
        """Test listing versions via API."""
        # Create architecture
        arch_response = client.post("/architectures", json=architecture_data)
        architecture_id = arch_response.json()["id"]

        # Create multiple versions
        for i in range(3):
            data = {**version_data, "version_number": f"1.{i}"}
            client.post(f"/architectures/{architecture_id}/versions", json=data)

        # List versions
        list_response = client.get(f"/architectures/{architecture_id}/versions")
        assert list_response.status_code == 200
        versions = list_response.json()
        assert len(versions) == 3


class TestResourceEndpoints:
    """Tests for resource endpoints."""

    @pytest.fixture
    def setup_version(self, client: TestClient, architecture_data, version_data):
        """Setup architecture and version for tests."""
        arch_response = client.post("/architectures", json=architecture_data)
        architecture_id = arch_response.json()["id"]

        version_response = client.post(
            f"/architectures/{architecture_id}/versions",
            json=version_data
        )
        version_id = version_response.json()["id"]

        return architecture_id, version_id

    def test_create_resource(self, client: TestClient, setup_version, resource_group_data):
        """Test creating a resource via API."""
        architecture_id, version_id = setup_version

        response = client.post(
            f"/architectures/{architecture_id}/versions/{version_id}/resources",
            json=resource_group_data
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == resource_group_data["name"]
        assert "id" in data

    def test_get_resource(self, client: TestClient, setup_version, resource_group_data):
        """Test getting a resource via API."""
        architecture_id, version_id = setup_version

        # Create resource
        create_response = client.post(
            f"/architectures/{architecture_id}/versions/{version_id}/resources",
            json=resource_group_data
        )
        resource_id = create_response.json()["id"]

        # Get resource
        get_response = client.get(
            f"/architectures/{architecture_id}/versions/{version_id}/resources/{resource_id}"
        )
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["id"] == resource_id

    def test_list_resources(self, client: TestClient, setup_version, resource_group_data):
        """Test listing resources via API."""
        architecture_id, version_id = setup_version

        # Create multiple resources
        for i in range(3):
            data = {**resource_group_data, "resource_key": f"rg-{i}", "name": f"rg-{i}"}
            client.post(
                f"/architectures/{architecture_id}/versions/{version_id}/resources",
                json=data
            )

        # List resources
        list_response = client.get(
            f"/architectures/{architecture_id}/versions/{version_id}/resources"
        )
        assert list_response.status_code == 200
        resources = list_response.json()
        assert len(resources) == 3


class TestCrossArchitectureValidation:
    """Tests for cross-architecture and cross-version validation."""

    def test_get_version_with_wrong_architecture_id(
        self, client: TestClient, architecture_data, version_data
    ):
        """Test that accessing version with wrong architecture_id returns 404."""
        from uuid import uuid4
        
        # Create architecture and version
        arch_response = client.post("/architectures", json=architecture_data)
        architecture_id = arch_response.json()["id"]

        version_response = client.post(
            f"/architectures/{architecture_id}/versions",
            json=version_data
        )
        version_id = version_response.json()["id"]

        # Try to access version with a different architecture_id
        wrong_arch_id = uuid4()
        get_response = client.get(
            f"/architectures/{wrong_arch_id}/versions/{version_id}"
        )
        assert get_response.status_code == 404
        assert "not found" in get_response.json()["detail"].lower()

    def test_create_resource_with_parent_from_different_version(
        self, client: TestClient, architecture_data, version_data, resource_group_data, vnet_data
    ):
        """Test that creating resource with parent from different version is rejected."""
        # Create first architecture and version
        arch1_response = client.post("/architectures", json=architecture_data)
        arch1_id = arch1_response.json()["id"]

        v1_response = client.post(
            f"/architectures/{arch1_id}/versions",
            json=version_data
        )
        v1_id = v1_response.json()["id"]

        # Create a resource group in v1
        rg_response = client.post(
            f"/architectures/{arch1_id}/versions/{v1_id}/resources",
            json=resource_group_data
        )
        resource_group_id = rg_response.json()["id"]

        # Create second version of same architecture
        v2_data = {**version_data, "version_number": "2.0"}
        v2_response = client.post(
            f"/architectures/{arch1_id}/versions",
            json=v2_data
        )
        v2_id = v2_response.json()["id"]

        # Try to create vnet in v2 with parent from v1 (should fail)
        vnet_with_parent = {**vnet_data, "parent_resource_id": str(resource_group_id)}
        create_response = client.post(
            f"/architectures/{arch1_id}/versions/{v2_id}/resources",
            json=vnet_with_parent
        )
        assert create_response.status_code == 400
        assert "parent" in create_response.json()["detail"].lower()

    def test_list_resources_with_wrong_architecture_id(
        self, client: TestClient, architecture_data, version_data
    ):
        """Test that listing resources with wrong architecture_id returns 404."""
        from uuid import uuid4
        
        # Create architecture and version
        arch_response = client.post("/architectures", json=architecture_data)
        architecture_id = arch_response.json()["id"]

        version_response = client.post(
            f"/architectures/{architecture_id}/versions",
            json=version_data
        )
        version_id = version_response.json()["id"]

        # Try to list resources with a different architecture_id
        wrong_arch_id = uuid4()
        list_response = client.get(
            f"/architectures/{wrong_arch_id}/versions/{version_id}/resources"
        )
        assert list_response.status_code == 404
        assert "not found" in list_response.json()["detail"].lower()
