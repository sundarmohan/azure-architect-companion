from __future__ import annotations

from typing import Any

import httpx

from .cache import TTLCache


class AzureRetailPricingAdapter:
    BASE_URL = "https://prices.azure.com/api/retail/prices"

    def __init__(self, *, cache: TTLCache[dict[str, Any]] | None = None) -> None:
        self._cache = cache or TTLCache(ttl_seconds=300)

    async def get_pricing(
        self,
        *,
        resource_type: str,
        region: str,
        sku: str | None,
        quantity: float,
    ) -> dict[str, Any]:
        arm_region = self._normalize_region(region)
        service_name = self._map_resource_to_service(resource_type)
        if not service_name:
            return {
                "unavailable": True,
                "error": "Unsupported Azure resource type mapping for pricing",
            }

        cache_key = f"{arm_region}|{service_name}|{(sku or '').strip().lower()}|{quantity}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        filters = [
            f"armRegionName eq '{arm_region}'",
            f"serviceName eq '{service_name}'",
            "priceType eq 'Consumption'",
        ]
        if sku:
            filters.append(f"armSkuName eq '{sku}'")

        params = {
            "$filter": " and ".join(filters),
            "$top": 100,
        }

        items: list[dict[str, Any]] = []
        next_url: str | None = self.BASE_URL

        async with httpx.AsyncClient(timeout=20.0) as client:
            while next_url:
                response = await client.get(next_url, params=params if next_url == self.BASE_URL else None)
                response.raise_for_status()
                payload = response.json() or {}
                page_items = payload.get("Items") or []
                if isinstance(page_items, list):
                    items.extend(page_items)
                next_url = payload.get("NextPageLink")
                params = None

        if not items:
            result = {
                "unavailable": True,
                "error": f"No Microsoft Retail Prices rows for service={service_name}, region={arm_region}, sku={sku or 'any'}",
            }
            self._cache.set(cache_key, result)
            return result

        selected = self._select_price_row(items, sku=sku)
        if not selected:
            result = {
                "unavailable": True,
                "error": "Unable to select a pricing row from Microsoft Retail Prices response",
            }
            self._cache.set(cache_key, result)
            return result

        normalized = self._normalize_price(
            price=float(selected.get("retailPrice") or 0.0),
            unit=str(selected.get("unitOfMeasure") or ""),
            quantity=quantity,
        )
        if normalized is None:
            result = {
                "unavailable": True,
                "error": f"Unsupported pricing unit for monthly normalization: {selected.get('unitOfMeasure')}",
            }
            self._cache.set(cache_key, result)
            return result

        result = {
            "unavailable": False,
            "pricing_source": "azure_retail_prices",
            "currency": str(selected.get("currencyCode") or "USD"),
            "sku": str(selected.get("armSkuName") or selected.get("skuName") or sku or ""),
            "meter_name": str(selected.get("meterName") or ""),
            "unit_of_measure": str(selected.get("unitOfMeasure") or ""),
            "monthly": round(normalized["monthly"], 2),
            "annual": round(normalized["annual"], 2),
        }
        self._cache.set(cache_key, result)
        return result

    def _select_price_row(self, items: list[dict[str, Any]], *, sku: str | None) -> dict[str, Any] | None:
        if sku:
            matches = [
                item
                for item in items
                if str(item.get("armSkuName") or "").strip().lower() == sku.strip().lower()
            ]
            if matches:
                items = matches

        valid = [item for item in items if float(item.get("retailPrice") or 0.0) >= 0.0]
        if not valid:
            return None
        return sorted(valid, key=lambda x: float(x.get("retailPrice") or 0.0))[0]

    def _normalize_region(self, region: str) -> str:
        value = str(region or "").strip().lower()
        if not value:
            return "eastus"
        region_map = {
            "east us": "eastus",
            "east us 2": "eastus2",
            "west us": "westus",
            "west us 2": "westus2",
            "west us 3": "westus3",
            "central us": "centralus",
            "north europe": "northeurope",
            "west europe": "westeurope",
            "uk south": "uksouth",
        }
        return region_map.get(value, value.replace(" ", ""))

    def _map_resource_to_service(self, resource_type: str) -> str:
        key = str(resource_type or "").strip().lower()
        service_map = {
            "vm": "Virtual Machines",
            "appservice": "Azure App Service",
            "appserviceplan": "Azure App Service",
            "storage": "Storage",
            "sql": "SQL Database",
            "sqlserver": "SQL Database",
            "container": "Container Apps",
            "containerenv": "Container Apps",
            "aks": "Azure Kubernetes Service",
            "keyvault": "Key Vault",
            "publicip": "Virtual Network",
            "natgateway": "Virtual Network",
            "vpn": "VPN Gateway",
            "gateway": "Application Gateway",
            "vnet": "Virtual Network",
            "subnet": "Virtual Network",
            "nsg": "Virtual Network",
            "bastion": "Azure Bastion",
            "privateendpoint": "Private Link",
            "firewall": "Azure Firewall",
            "loganalytics": "Log Analytics",
        }
        return service_map.get(key, "")

    def _normalize_price(self, *, price: float, unit: str, quantity: float) -> dict[str, float] | None:
        q = max(0.0, float(quantity or 1.0))
        normalized_unit = str(unit or "").lower()

        if "hour" in normalized_unit:
            monthly = price * 730 * q
            return {"monthly": monthly, "annual": monthly * 12}
        if "month" in normalized_unit:
            monthly = price * q
            return {"monthly": monthly, "annual": monthly * 12}
        if "day" in normalized_unit:
            monthly = price * 30 * q
            return {"monthly": monthly, "annual": monthly * 12}
        if "gb" in normalized_unit:
            # Treat GB rows as monthly per-GB where quantity is available.
            monthly = price * q
            return {"monthly": monthly, "annual": monthly * 12}
        return None
