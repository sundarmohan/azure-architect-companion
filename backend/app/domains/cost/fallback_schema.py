from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PricingRow:
    category: str
    tiers: dict[str, float]
    default_tier: str
    currency: str


_PRICING_INDEX: dict[str, PricingRow] | None = None


def _fallback_file_path() -> Path:
    return Path(__file__).resolve().parent / "azure.json"


def _load_pricing_index() -> dict[str, PricingRow]:
    global _PRICING_INDEX
    if _PRICING_INDEX is not None:
        return _PRICING_INDEX

    payload = json.loads(_fallback_file_path().read_text(encoding="utf-8"))
    schemas = payload.get("resource_schemas") or {}

    index: dict[str, PricingRow] = {}
    for type_id, raw in schemas.items():
        if not isinstance(raw, dict):
            continue
        pricing = raw.get("pricing") or {}
        if not isinstance(pricing, dict):
            continue
        tiers = pricing.get("tiers") or {}
        if not isinstance(tiers, dict) or not tiers:
            continue
        default_tier = str(pricing.get("default_tier") or next(iter(tiers.keys())))
        index[str(type_id)] = PricingRow(
            category=str(raw.get("category") or "Other"),
            tiers={str(k): float(v) for k, v in tiers.items() if k},
            default_tier=default_tier,
            currency=str(pricing.get("currency") or "USD"),
        )

    _PRICING_INDEX = index
    return index


def _region_multiplier(region: str) -> float:
    r = str(region or "").strip().lower()
    if r in {"westeurope", "uksouth", "northeurope"}:
        return 1.12
    if r in {"westus", "westus2", "westus3"}:
        return 1.05
    return 1.0


def estimate_monthly_cost(resource: dict[str, Any], *, region: str) -> dict[str, Any]:
    pricing_index = _load_pricing_index()
    resource_type = str(resource.get("resource_type") or "")

    candidate_keys = [
        resource_type,
        f"azure-{resource_type}",
        {
            "appservice": "azure-app",
            "container": "azure-container-apps",
            "containerenv": "azure-container-apps-environment",
            "keyvault": "azure-keyvault",
            "natgateway": "azure-nat-gateway",
            "privateendpoint": "azure-private-endpoint",
            "sql": "azure-sql",
            "sqlserver": "azure-sql-server",
            "vm": "azure-vm",
            "storage": "azure-storage",
            "gateway": "azure-application-gateway",
            "vpn": "azure-vpn-gateway",
            "bastion": "azure-bastion",
            "publicip": "azure-public-ip",
            "subnet": "azure-subnet",
            "vnet": "azure-vnet",
            "nsg": "azure-network-security-group",
            "loganalytics": "azure-log-analytics",
            "aks": "azure-aks",
        }.get(resource_type, ""),
    ]

    pricing_row = None
    for key in candidate_keys:
        if key and key in pricing_index:
            pricing_row = pricing_index[key]
            break

    if pricing_row is None:
        return {
            "pricing_source": "schema_fallback",
            "unavailable": True,
            "warning": "No fallback schema pricing metadata for this resource type",
        }

    sku = str(resource.get("sku") or "")
    if not sku:
        props = resource.get("properties") if isinstance(resource.get("properties"), dict) else {}
        sku = str(props.get("skuSize") or props.get("vmSize") or props.get("tier") or pricing_row.default_tier)

    base = pricing_row.tiers.get(sku, pricing_row.tiers.get(pricing_row.default_tier, 0.0))
    monthly = round(float(base) * _region_multiplier(region), 2)

    return {
        "pricing_source": "schema_fallback",
        "unavailable": False,
        "category": pricing_row.category,
        "sku": sku,
        "monthly": monthly,
        "annual": round(monthly * 12, 2),
        "currency": pricing_row.currency,
    }
