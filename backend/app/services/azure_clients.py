"""Read-only Azure SDK boundary for Resource Intelligence."""

from __future__ import annotations

from typing import Any, Protocol

from ..core.config import Settings


class AzureReadOnlyClient(Protocol):
    """Finite read-only surface consumed by M10."""

    def get_subscription(self) -> dict[str, Any]: ...
    def list_resource_groups(self) -> list[dict[str, Any]]: ...
    def list_locations(self) -> list[dict[str, Any]]: ...
    def list_resources(self) -> list[dict[str, Any]]: ...
    def list_providers(self) -> list[dict[str, Any]]: ...
    def list_resource_types(self) -> list[dict[str, Any]]: ...
    def list_skus(self) -> list[dict[str, Any]]: ...
    def list_quotas(self, regions: list[str]) -> list[dict[str, Any]]: ...


class AzureSdkReadOnlyClient:
    """Azure SDK implementation exposing discovery GET/list operations only."""

    def __init__(self, settings: Settings) -> None:
        if not settings.azure_subscription_id or not settings.azure_tenant_id:
            raise ValueError("Azure tenant and subscription configuration is required")
        try:
            from azure.identity import ClientSecretCredential, DefaultAzureCredential
            from azure.mgmt.compute import ComputeManagementClient
            from azure.mgmt.resource import ResourceManagementClient, SubscriptionClient
            from azure.mgmt.resourcegraph import ResourceGraphClient
        except ImportError as error:
            raise RuntimeError("Azure SDK dependencies are not installed") from error

        options = {
            "retry_total": settings.azure_intelligence_max_retries,
            "connection_timeout": settings.azure_intelligence_timeout_seconds,
            "read_timeout": settings.azure_intelligence_timeout_seconds,
        }
        if settings.azure_credential_mode.casefold() == "client_secret":
            if not settings.azure_client_id or not settings.azure_client_secret:
                raise ValueError("Client ID and client secret configuration is required")
            credential = ClientSecretCredential(
                tenant_id=settings.azure_tenant_id,
                client_id=settings.azure_client_id,
                client_secret=settings.azure_client_secret.get_secret_value(),
            )
        else:
            credential = DefaultAzureCredential(
                tenant_id=settings.azure_tenant_id,
                managed_identity_client_id=settings.azure_client_id,
                exclude_interactive_browser_credential=True,
            )
        self.subscription_id = settings.azure_subscription_id
        self._subscription = SubscriptionClient(credential, **options)
        self._resource = ResourceManagementClient(credential, self.subscription_id, **options)
        self._resource_graph = ResourceGraphClient(credential, **options)
        self._compute = ComputeManagementClient(credential, self.subscription_id, **options)

    def get_subscription(self) -> dict[str, Any]:
        item = self._subscription.subscriptions.get(self.subscription_id)
        return {
            "subscription_id": str(item.subscription_id),
            "display_name": item.display_name,
            "state": str(item.state) if item.state is not None else None,
        }

    def list_resource_groups(self) -> list[dict[str, Any]]:
        return [
            {"id": item.id, "name": item.name, "location": item.location}
            for item in self._resource.resource_groups.list()
        ]

    def list_locations(self) -> list[dict[str, Any]]:
        return [
            {
                "name": item.name,
                "display_name": item.display_name,
                "regional_display_name": item.regional_display_name,
                "aliases": [],
            }
            for item in self._subscription.subscriptions.list_locations(self.subscription_id)
        ]

    def list_resources(self) -> list[dict[str, Any]]:
        from azure.mgmt.resourcegraph.models import QueryRequest

        query = QueryRequest(
            subscriptions=[self.subscription_id],
            query="Resources | project id, name, type, location, resourceGroup, subscriptionId, sku, kind",
        )
        response = self._resource_graph.resources(query)
        return [dict(item) for item in (response.data or [])]

    def list_providers(self) -> list[dict[str, Any]]:
        return [
            {
                "namespace": item.namespace,
                "registration_state": item.registration_state,
            }
            for item in self._resource.providers.list()
        ]

    def list_resource_types(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for provider in self._resource.providers.list(expand="resourceTypes/aliases"):
            for resource_type in provider.resource_types or []:
                api_versions = list(resource_type.api_versions or [])
                records.append(
                    {
                        "provider_namespace": provider.namespace,
                        "resource_type": f"{provider.namespace}/{resource_type.resource_type}",
                        "api_versions": api_versions,
                        "preferred_api_version": api_versions[0] if api_versions else None,
                        "locations": list(resource_type.locations or []),
                        "capabilities": {},
                        "restrictions": [],
                        "source": "AZURE_RESOURCE_MANAGER",
                    }
                )
        return records

    def list_skus(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for sku in self._compute.resource_skus.list():
            capabilities = {
                item.name: item.value
                for item in (sku.capabilities or [])
                if item.name is not None
            }
            restrictions = [
                {
                    "type": str(item.type) if item.type is not None else None,
                    "reason_code": str(item.reason_code) if item.reason_code is not None else None,
                    "values": list((item.restriction_info.locations if item.restriction_info else None) or []),
                }
                for item in (sku.restrictions or [])
            ]
            records.append(
                {
                    "resource_type": f"Microsoft.Compute/{sku.resource_type}",
                    "name": sku.name,
                    "tier": sku.tier,
                    "family": sku.family,
                    "size": sku.size,
                    "locations": list(sku.locations or []),
                    "location_info": [
                        {"location": item.location, "zones": list(item.zones or [])}
                        for item in (sku.location_info or [])
                    ],
                    "capabilities": capabilities,
                    "restrictions": restrictions,
                    "source": "AZURE_COMPUTE_RESOURCE_SKUS",
                }
            )
        return records

    def list_quotas(self, regions: list[str]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for region in sorted(set(regions)):
            for usage in self._compute.usage.list(region):
                records.append(
                    {
                        "provider_namespace": "Microsoft.Compute",
                        "region": region,
                        "name": usage.name.value if usage.name else None,
                        "localized_name": usage.name.localized_value if usage.name else None,
                        "current_usage": usage.current_value,
                        "limit": usage.limit,
                        "unit": str(usage.unit) if usage.unit is not None else None,
                        "source": "AZURE_COMPUTE_USAGE",
                    }
                )
        return records
