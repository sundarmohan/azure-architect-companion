"""Minimal backend integration coverage required by the M9 designer."""

from app.main import create_app
from app.models import ResourceCatalog


def test_dependency_crud_and_analysis_routes_are_distinct():
    paths = {route.path for route in create_app().routes}
    assert "/architectures/{architecture_id}/versions/{version_id}/dependencies" in paths
    assert "/architectures/{architecture_id}/versions/{version_id}/dependency-analysis" in paths


def test_vite_development_origin_is_allowed(client):
    response = client.options(
        "/architectures",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_catalog_detail_exposes_existing_guidance(client, db):
    entry = ResourceCatalog(
        provider="azure",
        resource_type="test/type",
        display_name="Test resource",
        category="test",
        version="1.0",
        enabled=True,
    )
    db.add(entry)
    db.commit()

    response = client.get("/catalog/resources/test/type")

    assert response.status_code == 200
    assert response.json()["networking_requirements"] == []
    assert response.json()["security_requirements"] == []
    assert response.json()["monitoring_requirements"] == []
    assert response.json()["backup_requirements"] == []
