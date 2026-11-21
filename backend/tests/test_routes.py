from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.domains.architecture.catalog import classify_relationship_rule


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def create_architecture(client: TestClient, name: str) -> dict:
    response = client.post(
        "/api/architectures",
        json={"name": name, "provider": "azure", "environment": "draft", "status": "draft"},
    )
    assert response.status_code == 201
    return response.json()


def test_azure_capabilities_and_patterns_are_local_and_typed(client: TestClient):
    capabilities = client.get("/api/azure/resource-capabilities")
    assert capabilities.status_code == 200
    by_type = {item["resource_type"]: item for item in capabilities.json()}
    assert by_type["appservice"]["supports_vnet_integration"] is True
    assert by_type["appservice"]["can_be_placed_inside_subnet"] is False
    assert by_type["privateendpoint"]["allowed_parent_resource_types"] == ["subnet"]
    assert by_type["sql"]["can_be_private_endpoint_target"] is True

    patterns = client.get("/api/azure/architecture-patterns")
    assert patterns.status_code == 200
    assert any(item["pattern_id"] == "private-endpoint-placement" for item in patterns.json())

    conditional = classify_relationship_rule("appservice", "keyvault", "integrated_with")
    assert conditional["valid"] is True
    assert conditional["status"] == "CONDITIONAL"

    invalid = classify_relationship_rule("appservice", "appserviceplan", "contains")
    assert invalid["valid"] is False
    assert invalid["status"] == "INVALID"

    unknown = classify_relationship_rule("future-service", "sql", "connects_to")
    assert unknown["valid"] is True
    assert unknown["status"] == "UNKNOWN"


def test_architecture_crud(client: TestClient):
    created = create_architecture(client, f"arch-{uuid4()}")
    architecture_id = created["id"]

    fetched = client.get(f"/api/architectures/{architecture_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == architecture_id

    updated = client.put(f"/api/architectures/{architecture_id}", json={"name": "renamed-arch"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "renamed-arch"

    deleted = client.delete(f"/api/architectures/{architecture_id}")
    assert deleted.status_code == 204

    missing = client.get(f"/api/architectures/{architecture_id}")
    assert missing.status_code == 404


def test_subscriptions_resource_groups_and_ownership(client: TestClient):
    arch_a = create_architecture(client, f"arch-a-{uuid4()}")
    arch_b = create_architecture(client, f"arch-b-{uuid4()}")

    sub_a = client.post(f"/api/architectures/{arch_a['id']}/subscriptions", json={"name": "sub-a"})
    assert sub_a.status_code == 201
    sub_a_id = sub_a.json()["id"]

    rg_ok = client.post(
        f"/api/architectures/{arch_a['id']}/resource-groups",
        json={
            "name": "rg-a",
            "location": "East US",
            "subscription_id": sub_a_id,
            "position_x": 100,
            "position_y": 140,
        },
    )
    assert rg_ok.status_code == 201

    rg_bad = client.post(
        f"/api/architectures/{arch_b['id']}/resource-groups",
        json={"name": "rg-bad", "location": "East US", "subscription_id": sub_a_id},
    )
    assert rg_bad.status_code == 400

    cleanup_a = client.delete(f"/api/architectures/{arch_a['id']}")
    cleanup_b = client.delete(f"/api/architectures/{arch_b['id']}")
    assert cleanup_a.status_code == 204
    assert cleanup_b.status_code == 204


def test_subscription_create_is_idempotent_per_architecture_and_subscription_id(client: TestClient):
    architecture = create_architecture(client, f"arch-sub-idempotent-{uuid4()}")
    architecture_id = architecture["id"]

    first = client.post(
        f"/api/architectures/{architecture_id}/subscriptions",
        json={
            "name": "sub-one",
            "subscription_id": "sub-123",
            "tenant_id": "tenant-a",
        },
    )
    assert first.status_code == 201
    first_payload = first.json()

    second = client.post(
        f"/api/architectures/{architecture_id}/subscriptions",
        json={
            "name": "sub-one-renamed",
            "subscription_id": "SUB-123",
            "tenant_id": "tenant-b",
            "properties": {"managed": True},
        },
    )
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["id"] == first_payload["id"]
    assert second_payload["name"] == "sub-one-renamed"
    assert second_payload["tenant_id"] == "tenant-b"

    listed = client.get(f"/api/architectures/{architecture_id}/subscriptions")
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["subscription_id"] == "sub-123"

    cleanup = client.delete(f"/api/architectures/{architecture_id}")
    assert cleanup.status_code == 204


def test_resource_relationship_persistence_and_deletion(client: TestClient):
    architecture = create_architecture(client, f"arch-main-{uuid4()}")
    architecture_id = architecture["id"]

    subscription = client.post(f"/api/architectures/{architecture_id}/subscriptions", json={"name": "sub-main"})
    assert subscription.status_code == 201
    subscription_id = subscription.json()["id"]

    resource_group = client.post(
        f"/api/architectures/{architecture_id}/resource-groups",
        json={
            "name": "rg-main",
            "location": "East US",
            "subscription_id": subscription_id,
            "position_x": 120,
            "position_y": 180,
        },
    )
    assert resource_group.status_code == 201
    rg = resource_group.json()

    res_1 = client.post(
        f"/api/architectures/{architecture_id}/resources",
        json={
            "resource_type": "vnet",
            "azure_resource_type": "Microsoft.Network/virtualNetworks",
            "name": "vnet-1",
            "location": "East US",
            "resource_group_id": rg["id"],
            "position_x": 15,
            "position_y": 25,
        },
    )
    assert res_1.status_code == 201
    resource_1_id = res_1.json()["id"]

    res_2 = client.post(
        f"/api/architectures/{architecture_id}/resources",
        json={
            "resource_type": "subnet",
            "azure_resource_type": "Microsoft.Network/virtualNetworks/subnets",
            "name": "subnet-1",
            "location": "East US",
            "resource_group_id": rg["id"],
            "position_x": 35,
            "position_y": 45,
        },
    )
    assert res_2.status_code == 201
    resource_2_id = res_2.json()["id"]

    relationship = client.post(
        f"/api/architectures/{architecture_id}/relationships",
        json={
            "source_resource_id": resource_1_id,
            "target_resource_id": resource_2_id,
            "relationship_type": "connects_to",
        },
    )
    assert relationship.status_code == 201
    relationship_id = relationship.json()["id"]

    duplicate = client.post(
        f"/api/architectures/{architecture_id}/relationships",
        json={
            "source_resource_id": resource_1_id,
            "target_resource_id": resource_2_id,
            "relationship_type": "connects_to",
        },
    )
    assert duplicate.status_code == 400

    relationships = client.get(f"/api/architectures/{architecture_id}/relationships")
    assert relationships.status_code == 200
    assert any(item["id"] == relationship_id for item in relationships.json())

    move_group = client.put(
        f"/api/architectures/{architecture_id}/resource-groups/{rg['id']}",
        json={"position_x": 400, "position_y": 420},
    )
    assert move_group.status_code == 200
    assert move_group.json()["position_x"] == 400
    assert move_group.json()["position_y"] == 420

    move_resource = client.put(
        f"/api/architectures/{architecture_id}/resources/{resource_1_id}",
        json={"position_x": 111, "position_y": 222},
    )
    assert move_resource.status_code == 200
    assert move_resource.json()["position_x"] == 111
    assert move_resource.json()["position_y"] == 222

    delete_rel = client.delete(f"/api/architectures/{architecture_id}/relationships/{relationship_id}")
    assert delete_rel.status_code == 204

    rg_with_resource = client.delete(f"/api/architectures/{architecture_id}/resource-groups/{rg['id']}")
    assert rg_with_resource.status_code == 400

    delete_res_2 = client.delete(f"/api/architectures/{architecture_id}/resources/{resource_2_id}")
    delete_res_1 = client.delete(f"/api/architectures/{architecture_id}/resources/{resource_1_id}")
    assert delete_res_2.status_code == 204
    assert delete_res_1.status_code == 204

    delete_rg = client.delete(f"/api/architectures/{architecture_id}/resource-groups/{rg['id']}")
    assert delete_rg.status_code == 204

    cleanup = client.delete(f"/api/architectures/{architecture_id}")
    assert cleanup.status_code == 204


def test_invalid_references_return_4xx(client: TestClient):
    arch_a = create_architecture(client, f"arch-ref-a-{uuid4()}")
    arch_b = create_architecture(client, f"arch-ref-b-{uuid4()}")

    rg_b = client.post(
        f"/api/architectures/{arch_b['id']}/resource-groups",
        json={"name": "rg-b", "location": "East US"},
    )
    assert rg_b.status_code == 201
    rg_b_id = rg_b.json()["id"]

    cross_resource = client.post(
        f"/api/architectures/{arch_a['id']}/resources",
        json={
            "resource_type": "vm",
            "name": "vm-cross",
            "resource_group_id": rg_b_id,
        },
    )
    assert cross_resource.status_code == 400

    bad_rg = client.post(
        f"/api/architectures/{arch_a['id']}/resources",
        json={"resource_type": "vm", "name": "vm-missing", "resource_group_id": str(uuid4())},
    )
    assert bad_rg.status_code == 404

    dependencies = client.get(f"/api/architectures/{arch_a['id']}/dependencies")
    assert dependencies.status_code == 200
    assert any(item["resource_type"] == "sql" and item["dependency_type"] == "resource_group" for item in dependencies.json())

    cleanup_a = client.delete(f"/api/architectures/{arch_a['id']}")
    cleanup_b = client.delete(f"/api/architectures/{arch_b['id']}")
    assert cleanup_a.status_code == 204
    assert cleanup_b.status_code == 204


def test_azure_resource_catalog_endpoint(client: TestClient):
    response = client.get("/api/azure/resource-catalog")
    assert response.status_code == 200
    catalog = response.json()
    types = {item["resource_type"] for item in catalog}

    required_types = {
        "user",
        "firewall",
        "vnet",
        "subnet",
        "nsg",
        "gateway",
        "appservice",
        "appserviceplan",
        "storage",
        "sql",
        "sqlserver",
        "vm",
        "container",
        "containerenv",
        "aks",
        "keyvault",
        "publicip",
        "natgateway",
        "vpn",
        "bastion",
        "privateendpoint",
        "loganalytics",
    }
    assert required_types.issubset(types)


def test_relationship_validation_endpoint(client: TestClient):
    architecture = create_architecture(client, f"arch-rel-validate-{uuid4()}")
    architecture_id = architecture["id"]

    rg = client.post(
        f"/api/architectures/{architecture_id}/resource-groups",
        json={"name": "rg-rel", "location": "East US"},
    ).json()

    app_service = client.post(
        f"/api/architectures/{architecture_id}/resources",
        json={
            "resource_type": "appservice",
            "name": "app-rel",
            "resource_group_id": rg["id"],
            "location": "East US",
        },
    ).json()

    plan = client.post(
        f"/api/architectures/{architecture_id}/resources",
        json={
            "resource_type": "appserviceplan",
            "name": "plan-rel",
            "resource_group_id": rg["id"],
            "location": "East US",
        },
    ).json()

    valid = client.post(
        f"/api/architectures/{architecture_id}/validate-relationship",
        json={
            "source_resource_id": app_service["id"],
            "target_resource_id": plan["id"],
            "relationship_type": "depends_on",
        },
    )
    assert valid.status_code == 200
    assert valid.json()["valid"] is True

    invalid = client.post(
        f"/api/architectures/{architecture_id}/validate-relationship",
        json={
            "source_resource_id": app_service["id"],
            "target_resource_id": plan["id"],
            "relationship_type": "contains",
        },
    )
    assert invalid.status_code == 200
    assert invalid.json()["valid"] is False

    cleanup = client.delete(f"/api/architectures/{architecture_id}")
    assert cleanup.status_code == 204


def test_resource_hierarchy_parent_persistence(client: TestClient):
    architecture = create_architecture(client, f"arch-parent-{uuid4()}")
    architecture_id = architecture["id"]

    rg = client.post(
        f"/api/architectures/{architecture_id}/resource-groups",
        json={"name": "rg-parent", "location": "East US"},
    ).json()

    vnet = client.post(
        f"/api/architectures/{architecture_id}/resources",
        json={
            "resource_type": "vnet",
            "name": "vnet-parent",
            "resource_group_id": rg["id"],
            "location": "East US",
        },
    ).json()

    subnet = client.post(
        f"/api/architectures/{architecture_id}/resources",
        json={
            "resource_type": "subnet",
            "name": "subnet-parent",
            "resource_group_id": rg["id"],
            "parent_resource_id": vnet["id"],
            "location": "East US",
        },
    )
    assert subnet.status_code == 201
    subnet_id = subnet.json()["id"]

    app_response = client.post(
        f"/api/architectures/{architecture_id}/resources",
        json={
            "resource_type": "appservice",
            "name": "app-parent",
            "resource_group_id": rg["id"],
            "parent_resource_id": subnet_id,
            "location": "East US",
        },
    )
    assert app_response.status_code == 201
    app = app_response.json()
    assert app["parent_resource_id"] == subnet_id

    resources = client.get(f"/api/architectures/{architecture_id}/resources")
    assert resources.status_code == 200
    app_row = next(item for item in resources.json() if item["id"] == app["id"])
    assert app_row["parent_resource_id"] == subnet_id

    invalid_self_parent = client.put(
        f"/api/architectures/{architecture_id}/resources/{app['id']}",
        json={"parent_resource_id": app["id"]},
    )
    assert invalid_self_parent.status_code == 400

    cleanup = client.delete(f"/api/architectures/{architecture_id}")
    assert cleanup.status_code == 204


def test_resource_group_canvas_dimensions_and_shared_app_service_plan(client: TestClient):
    architecture = create_architecture(client, f"arch-canvas-{uuid4()}")
    architecture_id = architecture["id"]
    rg = client.post(
        f"/api/architectures/{architecture_id}/resource-groups",
        json={"name": "rg-canvas", "location": "East US", "properties": {"canvas_width": 900, "canvas_height": 700}},
    ).json()
    saved_group = client.put(
        f"/api/architectures/{architecture_id}/resource-groups/{rg['id']}",
        json={"properties": {"canvas_width": 960, "canvas_height": 720}},
    )
    assert saved_group.status_code == 200
    assert saved_group.json()["properties"] == {"canvas_width": 960, "canvas_height": 720}

    plan = client.post(
        f"/api/architectures/{architecture_id}/resources",
        json={"resource_type": "appserviceplan", "name": "plan-shared", "resource_group_id": rg["id"]},
    ).json()
    apps = [
        client.post(
            f"/api/architectures/{architecture_id}/resources",
            json={"resource_type": "appservice", "name": f"app-{index}", "resource_group_id": rg["id"], "properties": {"plan_resource_id": plan["id"]}},
        ).json()
        for index in range(2)
    ]
    for app in apps:
        relationship = client.post(
            f"/api/architectures/{architecture_id}/relationships",
            json={"source_resource_id": app["id"], "target_resource_id": plan["id"], "relationship_type": "depends_on"},
        )
        assert relationship.status_code == 201

    relationships = client.get(f"/api/architectures/{architecture_id}/relationships").json()
    assert {(item["source_resource_id"], item["target_resource_id"], item["relationship_type"]) for item in relationships} == {
        (apps[0]["id"], plan["id"], "depends_on"),
        (apps[1]["id"], plan["id"], "depends_on"),
    }
    duplicate = client.post(
        f"/api/architectures/{architecture_id}/relationships",
        json={"source_resource_id": apps[0]["id"], "target_resource_id": plan["id"], "relationship_type": "depends_on"},
    )
    assert duplicate.status_code == 400

    cleanup = client.delete(f"/api/architectures/{architecture_id}")
    assert cleanup.status_code == 204
