from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx

try:
    from azure.identity import ClientSecretCredential
except Exception:  # pragma: no cover - optional dependency guard
    ClientSecretCredential = None  # type: ignore[assignment]


class AzureResourceDiscoveryAdapter:
    SUBSCRIPTION_API_VERSION = "2020-01-01"
    RESOURCE_GROUPS_API_VERSION = "2021-04-01"
    RESOURCES_API_VERSION = "2021-04-01"

    TYPE_MAP = {
        "microsoft.network/virtualnetworks": "vnet",
        "microsoft.network/virtualnetworks/subnets": "subnet",
        "microsoft.network/networksecuritygroups": "nsg",
        "microsoft.network/publicipaddresses": "publicip",
        "microsoft.network/natgateways": "natgateway",
        "microsoft.network/azurefirewalls": "firewall",
        "microsoft.network/applicationgateways": "gateway",
        "microsoft.web/sites": "appservice",
        "microsoft.web/serverfarms": "appserviceplan",
        "microsoft.storage/storageaccounts": "storage",
        "microsoft.sql/servers": "sqlserver",
        "microsoft.sql/servers/databases": "sql",
        "microsoft.compute/virtualmachines": "vm",
        "microsoft.app/containerapps": "container",
        "microsoft.app/managedenvironments": "containerenv",
        "microsoft.containerservice/managedclusters": "aks",
        "microsoft.keyvault/vaults": "keyvault",
        "microsoft.network/virtualnetworkgateways": "vpn",
        "microsoft.network/bastionhosts": "bastion",
        "microsoft.network/privateendpoints": "privateendpoint",
        "microsoft.operationalinsights/workspaces": "loganalytics",
    }

    async def discover_subscription_resources(self, *, subscription_id: str) -> dict[str, Any]:
        if ClientSecretCredential is None:
            return {
                "success": False,
                "connection_state": "not_configured",
                "error": "azure-identity is not installed; Azure discovery is unavailable",
            }

        tenant_id = (os.getenv("AZURE_TENANT_ID") or "").strip()
        client_id = (os.getenv("AZURE_CLIENT_ID") or "").strip()
        client_secret = (os.getenv("AZURE_CLIENT_SECRET") or "").strip()

        if not tenant_id or not client_id or not client_secret:
            return {
                "success": False,
                "connection_state": "not_configured",
                "error": "Azure credentials are not configured for discovery",
            }

        try:
            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
            )
            token = credential.get_token("https://management.azure.com/.default")
        except Exception as exc:
            return {
                "success": False,
                "connection_state": "authentication_failure",
                "error": f"Azure authentication failed for discovery: {exc}",
            }

        headers = {
            "Authorization": f"Bearer {token.token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                status_response = await client.get(
                    f"https://management.azure.com/subscriptions/{subscription_id}",
                    params={"api-version": self.SUBSCRIPTION_API_VERSION},
                    headers=headers,
                )
                if status_response.status_code == 401:
                    return {
                        "success": False,
                        "connection_state": "authentication_failure",
                        "error": "Azure authentication failed for subscription access",
                    }
                if status_response.status_code == 403:
                    return {
                        "success": False,
                        "connection_state": "permission_failure",
                        "error": "Azure permissions are insufficient for subscription discovery",
                    }
                if status_response.status_code >= 400:
                    return {
                        "success": False,
                        "connection_state": "azure_api_failure",
                        "error": self._api_error_message(status_response),
                    }
                subscription_payload = status_response.json() or {}

                groups_response = await self._collect_paged(
                    client=client,
                    url=f"https://management.azure.com/subscriptions/{subscription_id}/resourcegroups",
                    api_version=self.RESOURCE_GROUPS_API_VERSION,
                    headers=headers,
                )
                if groups_response["connection_state"] != "configured_connected":
                    return groups_response

                resources_response = await self._collect_paged(
                    client=client,
                    url=f"https://management.azure.com/subscriptions/{subscription_id}/resources",
                    api_version=self.RESOURCES_API_VERSION,
                    headers=headers,
                )
                if resources_response["connection_state"] != "configured_connected":
                    return resources_response

        except httpx.TimeoutException:
            return {
                "success": False,
                "connection_state": "azure_api_failure",
                "error": "Azure resource discovery timed out",
            }
        except Exception as exc:
            return {
                "success": False,
                "connection_state": "azure_api_failure",
                "error": f"Azure API failure during discovery: {exc}",
            }

        normalized_groups = [self._normalize_group(item, subscription_id) for item in groups_response["items"]]

        normalized_resources: list[dict[str, Any]] = []
        unsupported_count = 0
        skipped_without_group = 0

        for item in resources_response["items"]:
            normalized = self._normalize_resource(item, subscription_id)
            if normalized is None:
                unsupported_count += 1
                continue
            if not normalized.get("resource_group_name"):
                skipped_without_group += 1
                continue
            normalized_resources.append(normalized)

        return {
            "success": True,
            "connection_state": "configured_connected",
            "subscription": {
                "id": str(subscription_payload.get("subscriptionId") or subscription_id),
                "name": str(subscription_payload.get("displayName") or ""),
                "state": str(subscription_payload.get("state") or ""),
            },
            "resource_groups": normalized_groups,
            "resources": normalized_resources,
            "unsupported_resources": unsupported_count,
            "skipped_without_group": skipped_without_group,
        }

    async def _collect_paged(
        self,
        *,
        client: httpx.AsyncClient,
        url: str,
        api_version: str,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        next_url: str | None = url
        params: dict[str, str] | None = {"api-version": api_version}

        expected_path = urlsplit(url).path.casefold()
        visited = set()
        while next_url:
            if not isinstance(next_url, str):
                return self._invalid_page()
            target = urlsplit(next_url)
            if (target.scheme != "https" or target.netloc != "management.azure.com"
                    or target.path.casefold() != expected_path or target.fragment
                    or next_url in visited or len(visited) >= 200):
                return self._invalid_page()
            visited.add(next_url)
            response = await client.get(next_url, params=params, headers=headers)
            if response.status_code == 401:
                return {
                    "success": False,
                    "connection_state": "authentication_failure",
                    "error": "Azure authentication failed while listing resources",
                }
            if response.status_code == 403:
                return {
                    "success": False,
                    "connection_state": "permission_failure",
                    "error": "Azure permissions are insufficient for resource discovery",
                }
            if response.status_code >= 400:
                return {
                    "success": False,
                    "connection_state": "azure_api_failure",
                    "error": self._api_error_message(response),
                }

            payload = response.json()
            if not isinstance(payload, dict):
                return self._invalid_page()
            page_items = payload.get("value")
            if (not isinstance(page_items, list) or len(items) + len(page_items) > 25000
                    or any(not isinstance(item, dict) for item in page_items)):
                return self._invalid_page()
            items.extend(page_items)
            next_url = payload.get("nextLink")
            if next_url is not None and (not isinstance(next_url, str) or not next_url):
                return self._invalid_page()
            params = None

        return {
            "success": True,
            "connection_state": "configured_connected",
            "items": items,
        }

    @staticmethod
    def _invalid_page() -> dict[str, Any]:
        return {
            "success": False,
            "connection_state": "azure_api_failure",
            "error": "Azure inventory pagination was invalid or exceeded collection limits",
        }

    def _normalize_group(self, item: dict[str, Any], subscription_id: str) -> dict[str, Any]:
        return {
            "azure_resource_id": str(item.get("id") or ""),
            "name": str(item.get("name") or ""),
            "location": str(item.get("location") or ""),
            "subscription_id": subscription_id,
            "tags": item.get("tags") if isinstance(item.get("tags"), dict) else {},
            "properties": item.get("properties") if isinstance(item.get("properties"), dict) else {},
        }

    def _normalize_resource(self, item: dict[str, Any], subscription_id: str) -> dict[str, Any] | None:
        azure_type = str(item.get("type") or "").strip()
        monitorai_type = self.TYPE_MAP.get(azure_type.lower())
        if not monitorai_type:
            return None

        azure_id = str(item.get("id") or "")
        resource_group_name = self._extract_resource_group_name(azure_id)
        parent_azure_id = self._extract_parent_resource_id(azure_id, azure_type)

        sku = self._extract_sku(item)
        properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}

        return {
            "azure_resource_id": azure_id,
            "azure_resource_type": azure_type,
            "resource_type": monitorai_type,
            "name": str(item.get("name") or ""),
            "location": str(item.get("location") or ""),
            "resource_group_name": resource_group_name,
            "subscription_id": subscription_id,
            "sku": sku,
            "parent_azure_resource_id": parent_azure_id,
            "properties": properties,
        }

    def _extract_resource_group_name(self, resource_id: str) -> str | None:
        lowered = resource_id.lower()
        marker = "/resourcegroups/"
        if marker not in lowered:
            return None
        tail = resource_id[lowered.index(marker) + len(marker) :]
        name = tail.split("/", 1)[0].strip()
        return name or None

    def _extract_parent_resource_id(self, resource_id: str, azure_type: str) -> str | None:
        lowered_id = resource_id.lower()
        lowered_type = azure_type.lower()

        if lowered_type == "microsoft.network/virtualnetworks/subnets" and "/subnets/" in lowered_id:
            return resource_id.rsplit("/subnets/", 1)[0]
        if lowered_type == "microsoft.sql/servers/databases" and "/databases/" in lowered_id:
            return resource_id.rsplit("/databases/", 1)[0]
        return None

    def _extract_sku(self, item: dict[str, Any]) -> str | None:
        raw_sku = item.get("sku")
        if isinstance(raw_sku, dict):
            if raw_sku.get("name"):
                return str(raw_sku.get("name"))
            if raw_sku.get("tier"):
                return str(raw_sku.get("tier"))
        if raw_sku:
            return str(raw_sku)
        return None

    def _api_error_message(self, response: httpx.Response) -> str:
        try:
            payload = response.json() or {}
            if isinstance(payload, dict):
                inner = payload.get("error")
                if isinstance(inner, dict) and inner.get("message"):
                    return str(inner.get("message"))
                if payload.get("message"):
                    return str(payload.get("message"))
        except Exception:
            pass
        return f"Azure API request failed with status {response.status_code}"


class AzureResourceDiscoveryService:
    async def sync_discovered_resources(
        self,
        *,
        architecture_id: Any,
        subscription: Any,
        discovered: dict[str, Any],
        db: Any,
        resource_model: Any,
        resource_group_model: Any,
    ) -> dict[str, Any]:
        from sqlalchemy import select

        groups_result = await db.execute(
            select(resource_group_model)
            .where(resource_group_model.architecture_id == architecture_id)
        )
        existing_groups = list(groups_result.scalars().all())

        resources_result = await db.execute(
            select(resource_model)
            .where(resource_model.architecture_id == architecture_id)
        )
        existing_resources = list(resources_result.scalars().all())

        now_iso = datetime.now(timezone.utc).isoformat()

        groups_by_azure: dict[str, Any] = {}
        groups_by_name: dict[tuple[str, str], Any] = {}
        for group in existing_groups:
            props = group.properties or {}
            azure_id = str(props.get("azure_resource_id") or "").strip().lower()
            if azure_id:
                groups_by_azure[azure_id] = group
            groups_by_name[(group.name.strip().lower(), str(group.subscription_id or ""))] = group

        resource_groups_created = 0
        resource_groups_updated = 0

        discovered_groups = discovered.get("resource_groups") or []
        for index, group_data in enumerate(discovered_groups):
            azure_group_id = str(group_data.get("azure_resource_id") or "").strip()
            group_name = str(group_data.get("name") or "").strip()
            if not group_name:
                continue

            existing_group = None
            if azure_group_id:
                existing_group = groups_by_azure.get(azure_group_id.lower())
            if existing_group is None:
                existing_group = groups_by_name.get((group_name.lower(), str(subscription.id)))

            if existing_group is None:
                existing_group = resource_group_model(
                    architecture_id=architecture_id,
                    name=group_name,
                    location=str(group_data.get("location") or ""),
                    subscription_id=subscription.id,
                    position_x=80 + (index % 3) * 620,
                    position_y=120 + (index // 3) * 440,
                    tags=group_data.get("tags") or {},
                    properties={
                        "azure_resource_id": azure_group_id,
                        "azure_subscription_id": subscription.subscription_id,
                        "discovery_managed": True,
                        "discovery_last_seen_at": now_iso,
                    },
                )
                db.add(existing_group)
                resource_groups_created += 1
            else:
                existing_group.location = str(group_data.get("location") or existing_group.location)
                existing_group.subscription_id = subscription.id
                existing_group.tags = group_data.get("tags") or existing_group.tags or {}
                props = existing_group.properties or {}
                props.update(
                    {
                        "azure_resource_id": azure_group_id or props.get("azure_resource_id"),
                        "azure_subscription_id": subscription.subscription_id,
                        "discovery_managed": True,
                        "discovery_last_seen_at": now_iso,
                    }
                )
                existing_group.properties = props
                resource_groups_updated += 1

            if azure_group_id:
                groups_by_azure[azure_group_id.lower()] = existing_group

        await db.flush()

        group_name_to_id: dict[str, Any] = {}
        for group_data in discovered_groups:
            azure_group_id = str(group_data.get("azure_resource_id") or "").strip().lower()
            group_name = str(group_data.get("name") or "").strip().lower()
            if azure_group_id and azure_group_id in groups_by_azure:
                group_name_to_id[group_name] = groups_by_azure[azure_group_id].id
                continue
            named_group = groups_by_name.get((group_name, str(subscription.id)))
            if named_group is not None:
                group_name_to_id[group_name] = named_group.id

        resources_by_azure: dict[str, Any] = {}
        for resource in existing_resources:
            props = resource.properties or {}
            azure_id = str(props.get("azure_resource_id") or "").strip().lower()
            if not azure_id:
                continue
            azure_subscription_id = str(props.get("azure_subscription_id") or "").strip().lower()
            if azure_subscription_id and azure_subscription_id != str(subscription.subscription_id or "").strip().lower():
                continue
            resources_by_azure[azure_id] = resource

        resources_created = 0
        resources_updated = 0
        hierarchy_links_updated = 0
        normalized_resources: list[dict[str, Any]] = []

        discovered_resources = discovered.get("resources") or []
        pending_parent_links: list[tuple[str, str]] = []

        for index, discovered_resource in enumerate(discovered_resources):
            azure_resource_id = str(discovered_resource.get("azure_resource_id") or "").strip()
            if not azure_resource_id:
                continue

            resource_group_name = str(discovered_resource.get("resource_group_name") or "").strip().lower()
            resource_group_id = group_name_to_id.get(resource_group_name)
            if resource_group_id is None:
                continue

            existing_resource = resources_by_azure.get(azure_resource_id.lower())
            properties = existing_resource.properties if existing_resource is not None else {}
            properties = properties or {}
            properties.update(
                {
                    "azure_resource_id": azure_resource_id,
                    "azure_subscription_id": subscription.subscription_id,
                    "azure_resource_group_name": discovered_resource.get("resource_group_name"),
                    "discovery_managed": True,
                    "discovery_last_seen_at": now_iso,
                }
            )
            if discovered_resource.get("parent_azure_resource_id"):
                properties["parent_azure_resource_id"] = discovered_resource.get("parent_azure_resource_id")

            if existing_resource is None:
                existing_resource = resource_model(
                    architecture_id=architecture_id,
                    resource_type=str(discovered_resource.get("resource_type") or ""),
                    azure_resource_type=str(discovered_resource.get("azure_resource_type") or ""),
                    name=str(discovered_resource.get("name") or ""),
                    location=str(discovered_resource.get("location") or "") or None,
                    resource_group_id=resource_group_id,
                    sku=discovered_resource.get("sku"),
                    position_x=120 + (index % 4) * 170,
                    position_y=140 + (index // 4) * 110,
                    properties=properties,
                )
                db.add(existing_resource)
                resources_created += 1
                action = "created"
            else:
                existing_resource.resource_type = str(discovered_resource.get("resource_type") or existing_resource.resource_type)
                existing_resource.azure_resource_type = str(discovered_resource.get("azure_resource_type") or existing_resource.azure_resource_type or "")
                existing_resource.name = str(discovered_resource.get("name") or existing_resource.name)
                existing_resource.location = str(discovered_resource.get("location") or existing_resource.location or "") or None
                existing_resource.resource_group_id = resource_group_id
                existing_resource.sku = discovered_resource.get("sku") or existing_resource.sku
                existing_resource.properties = properties
                resources_updated += 1
                action = "updated"

            resources_by_azure[azure_resource_id.lower()] = existing_resource
            normalized_resources.append(
                {
                    "azure_resource_id": azure_resource_id,
                    "resource_type": existing_resource.resource_type,
                    "name": existing_resource.name,
                    "resource_group_name": discovered_resource.get("resource_group_name"),
                    "parent_azure_resource_id": discovered_resource.get("parent_azure_resource_id"),
                    "action": action,
                }
            )

            parent_azure_resource_id = str(discovered_resource.get("parent_azure_resource_id") or "").strip()
            if parent_azure_resource_id:
                pending_parent_links.append((azure_resource_id, parent_azure_resource_id))

        for child_azure_id, parent_azure_id in pending_parent_links:
            child = resources_by_azure.get(child_azure_id.lower())
            parent = resources_by_azure.get(parent_azure_id.lower())
            if child is None or parent is None:
                continue
            if child.id == parent.id:
                continue
            if child.parent_resource_id != parent.id:
                child.parent_resource_id = parent.id
                hierarchy_links_updated += 1

        await db.commit()

        return {
            "resource_groups_discovered": len(discovered_groups),
            "resources_discovered": len(discovered_resources),
            "resource_groups_created": resource_groups_created,
            "resource_groups_updated": resource_groups_updated,
            "resources_created": resources_created,
            "resources_updated": resources_updated,
            "hierarchy_links_updated": hierarchy_links_updated,
            "unsupported_resources": int(discovered.get("unsupported_resources") or 0),
            "skipped_without_group": int(discovered.get("skipped_without_group") or 0),
            "normalized_resources": normalized_resources,
        }
