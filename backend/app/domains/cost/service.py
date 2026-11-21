from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any
from uuid import UUID

from app.domains.architecture.models import Architecture, ArchitectureResource, AzureResourceGroup, AzureSubscription

from .azure_cost_management_adapter import AzureCostManagementAdapter
from .azure_retail_adapter import AzureRetailPricingAdapter
from .fallback_schema import estimate_monthly_cost
from .schemas import (
    ArchitectureActualCostRead,
    ArchitectureCostEstimateRead,
    ActualCostDailyItem,
    CostBreakdown,
    CostEstimateItem,
)


def _provider_from_resource(resource: dict[str, Any], default_provider: str = "azure") -> str:
    rtype = str(resource.get("resource_type") or "").strip().lower()
    if rtype.startswith("aws-"):
        return "aws"
    if rtype.startswith("gcp-"):
        return "gcp"
    return str(default_provider or "azure").lower()


def _resource_region(resource: dict[str, Any], default_region: str) -> str:
    return str(resource.get("location") or resource.get("region") or default_region or "eastus")


def _resource_sku(resource: dict[str, Any]) -> str | None:
    if resource.get("sku"):
        return str(resource.get("sku"))
    props = resource.get("properties") or {}
    if isinstance(props, dict):
        for key in ("skuSize", "vmSize", "tier", "computeSize", "serviceTier"):
            if props.get(key):
                return str(props.get(key))
    return None


def _resource_quantity(resource: dict[str, Any]) -> float:
    props = resource.get("properties") if isinstance(resource.get("properties"), dict) else {}
    for key in ("quantity", "size_gb", "storage_gb", "capacity_gb", "disk_size_gb", "nodeCount", "instances"):
        value = props.get(key)
        try:
            if value is not None:
                parsed = float(value)
                if parsed > 0:
                    return parsed
        except Exception:
            continue
    return 1.0


async def _call_provider_pricing(
    adapter: AzureRetailPricingAdapter,
    *,
    provider: str,
    resource_type: str,
    region: str,
    sku: str | None,
    quantity: float,
) -> dict[str, Any]:
    if provider != "azure":
        return {
            "unavailable": True,
            "error": f"Provider '{provider}' is not supported in V2.6.1 estimated Azure cost endpoint",
        }
    try:
        return await adapter.get_pricing(
            resource_type=resource_type,
            region=region,
            sku=sku,
            quantity=quantity,
        )
    except Exception as exc:
        return {
            "unavailable": True,
            "error": f"Azure Retail Prices API call failed: {exc}",
        }


class CostEstimationService:
    def __init__(
        self,
        *,
        adapter: AzureRetailPricingAdapter | None = None,
        actual_adapter: AzureCostManagementAdapter | None = None,
    ) -> None:
        self._adapter = adapter or AzureRetailPricingAdapter()
        self._actual_adapter = actual_adapter or AzureCostManagementAdapter()

    async def estimate_architecture_cost(
        self,
        *,
        architecture: Architecture,
        resources: Sequence[ArchitectureResource],
        resource_groups: Sequence[AzureResourceGroup],
        subscriptions: Sequence[AzureSubscription] | None = None,
        region_override: str | None = None,
    ) -> ArchitectureCostEstimateRead:
        groups_by_id = {str(item.id): item for item in resource_groups}
        subs_by_db_id = {str(item.id): item for item in (subscriptions or [])}
        default_region = str(region_override or architecture.default_region or "eastus")

        items: list[CostEstimateItem] = []
        warnings: list[str] = []
        errors: list[str] = []
        by_type: dict[str, float] = {}
        by_group: dict[str, float] = {}
        by_subscription: dict[str, float] = {}
        any_fallback = False

        normalized_resources = [
            {
                "id": str(resource.id),
                "name": resource.name,
                "resource_type": resource.resource_type,
                "sku": resource.sku,
                "resource_group_id": str(resource.resource_group_id) if resource.resource_group_id else None,
                "properties": resource.properties or {},
                "location": resource.location
                or (groups_by_id.get(str(resource.resource_group_id)).location if resource.resource_group_id and groups_by_id.get(str(resource.resource_group_id)) else None),
            }
            for resource in resources
        ]

        for resource in normalized_resources:
            provider = _provider_from_resource(resource, architecture.provider)
            region = _resource_region(resource, default_region)
            sku = _resource_sku(resource)
            quantity = _resource_quantity(resource)
            group = groups_by_id.get(str(resource.get("resource_group_id") or "")) if resource.get("resource_group_id") else None
            subscription = subs_by_db_id.get(str(group.subscription_id)) if group and group.subscription_id else None
            group_key = str(group.name) if group else "unassigned"
            subscription_key = str(subscription.subscription_id) if subscription and subscription.subscription_id else "unassigned"

            live_pricing = await _call_provider_pricing(
                self._adapter,
                provider=provider,
                resource_type=str(resource.get("resource_type") or ""),
                region=region,
                sku=sku,
                quantity=quantity,
            )

            if not live_pricing.get("unavailable"):
                item = CostEstimateItem(
                    resource_id=str(resource.get("id") or ""),
                    name=str(resource.get("name") or resource.get("resource_type") or "resource"),
                    resource_type=str(resource.get("resource_type") or ""),
                    region=region,
                    resource_group_id=str(group.id) if group else None,
                    resource_group_name=str(group.name) if group else None,
                    subscription_id=str(subscription.subscription_id) if subscription and subscription.subscription_id else None,
                    sku=live_pricing.get("sku") or sku,
                    quantity=quantity,
                    meter_name=live_pricing.get("meter_name"),
                    unit_of_measure=live_pricing.get("unit_of_measure"),
                    monthly_cost=round(float(live_pricing.get("monthly") or 0.0), 2),
                    annual_cost=round(float(live_pricing.get("annual") or 0.0), 2),
                    currency=str(live_pricing.get("currency") or "USD"),
                    pricing_source="azure_retail_prices",
                )
                items.append(item)
                by_type[item.resource_type] = by_type.get(item.resource_type, 0.0) + item.monthly_cost
                by_group[group_key] = by_group.get(group_key, 0.0) + item.monthly_cost
                by_subscription[subscription_key] = by_subscription.get(subscription_key, 0.0) + item.monthly_cost
                continue

            fallback = estimate_monthly_cost(resource, region=region)
            any_fallback = True
            warning = str(live_pricing.get("error") or "Live pricing unavailable, using schema fallback")
            warnings.append(f"{resource.get('name')}: {warning}")

            if fallback.get("unavailable"):
                errors.append(f"{resource.get('name')}: {fallback.get('warning')}")
                item = CostEstimateItem(
                    resource_id=str(resource.get("id") or ""),
                    name=str(resource.get("name") or resource.get("resource_type") or "resource"),
                    resource_type=str(resource.get("resource_type") or ""),
                    region=region,
                    resource_group_id=str(group.id) if group else None,
                    resource_group_name=str(group.name) if group else None,
                    subscription_id=str(subscription.subscription_id) if subscription and subscription.subscription_id else None,
                    sku=sku,
                    quantity=quantity,
                    monthly_cost=0.0,
                    annual_cost=0.0,
                    currency="USD",
                    pricing_source="schema_fallback",
                    warning=str(fallback.get("warning") or "Fallback pricing unavailable"),
                    error=warning,
                )
                items.append(item)
                by_type[item.resource_type] = by_type.get(item.resource_type, 0.0) + item.monthly_cost
                by_group[group_key] = by_group.get(group_key, 0.0) + item.monthly_cost
                by_subscription[subscription_key] = by_subscription.get(subscription_key, 0.0) + item.monthly_cost
                continue

            item = CostEstimateItem(
                resource_id=str(resource.get("id") or ""),
                name=str(resource.get("name") or resource.get("resource_type") or "resource"),
                resource_type=str(resource.get("resource_type") or ""),
                region=region,
                resource_group_id=str(group.id) if group else None,
                resource_group_name=str(group.name) if group else None,
                subscription_id=str(subscription.subscription_id) if subscription and subscription.subscription_id else None,
                sku=fallback.get("sku") or sku,
                quantity=quantity,
                monthly_cost=round(float(fallback.get("monthly") or 0.0), 2),
                annual_cost=round(float(fallback.get("annual") or 0.0), 2),
                currency=str(fallback.get("currency") or "USD"),
                pricing_source="schema_fallback",
                warning=warning,
            )
            items.append(item)
            by_type[item.resource_type] = by_type.get(item.resource_type, 0.0) + item.monthly_cost
            by_group[group_key] = by_group.get(group_key, 0.0) + item.monthly_cost
            by_subscription[subscription_key] = by_subscription.get(subscription_key, 0.0) + item.monthly_cost

        total_monthly = round(sum(item.monthly_cost for item in items), 2)
        total_annual = round(sum(item.annual_cost for item in items), 2)
        currency = items[0].currency if items else "USD"

        return ArchitectureCostEstimateRead(
            architecture_id=str(architecture.id),
            pricing_source="schema_fallback" if any_fallback else "azure_retail_prices",
            total_monthly_cost=total_monthly,
            total_annual_cost=total_annual,
            currency=currency,
            items=sorted(items, key=lambda x: x.monthly_cost, reverse=True),
            breakdown=CostBreakdown(
                by_resource_type={k: round(v, 2) for k, v in by_type.items()},
                by_resource_group={k: round(v, 2) for k, v in by_group.items()},
                by_subscription={k: round(v, 2) for k, v in by_subscription.items()},
            ),
            warnings=warnings,
            errors=errors,
        )

    async def get_architecture_actual_cost(
        self,
        *,
        architecture: Architecture,
        subscriptions: Sequence[AzureSubscription],
        requested_subscription_id: str | None,
        start_date: date | None,
        end_date: date | None,
    ) -> ArchitectureActualCostRead:
        allowed_subscription_ids = {
            str(sub.subscription_id).strip()
            for sub in subscriptions
            if sub.subscription_id and str(sub.subscription_id).strip()
        }

        requested = str(requested_subscription_id).strip() if requested_subscription_id else None
        if requested and requested not in allowed_subscription_ids:
            return ArchitectureActualCostRead(
                architecture_id=str(architecture.id),
                available=False,
                subscription_id=requested,
                start_date=(start_date.isoformat() if start_date else None),
                end_date=(end_date.isoformat() if end_date else None),
                error="Requested subscription does not belong to this architecture",
            )

        subscription_id = requested or self._resolve_subscription_id(subscriptions)
        start = start_date or self._actual_adapter.default_start_date()
        end = end_date or self._actual_adapter.default_end_date()

        result = await self._actual_adapter.get_actual_cost(
            subscription_id=subscription_id or "",
            start_date=start,
            end_date=end,
        )

        if not result.get("available"):
            return ArchitectureActualCostRead(
                architecture_id=str(architecture.id),
                available=False,
                subscription_id=subscription_id,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                error=str(result.get("error") or "Actual cost unavailable"),
            )

        return ArchitectureActualCostRead(
            architecture_id=str(architecture.id),
            available=True,
            subscription_id=str(result.get("subscription_id") or subscription_id or ""),
            currency=str(result.get("currency") or "USD"),
            total_cost=round(float(result.get("total_cost") or 0.0), 2),
            start_date=str(result.get("from") or start.isoformat()),
            end_date=str(result.get("to") or end.isoformat()),
            daily=[
                ActualCostDailyItem(
                    usage_date=str(item.get("usage_date") or ""),
                    cost=round(float(item.get("cost") or 0.0), 2),
                )
                for item in (result.get("daily") or [])
                if isinstance(item, dict)
            ],
        )

    def _resolve_subscription_id(self, subscriptions: Sequence[AzureSubscription]) -> str | None:
        for sub in subscriptions:
            if sub.subscription_id:
                return str(sub.subscription_id)
        return None
