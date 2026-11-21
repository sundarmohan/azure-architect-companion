"""Reused HIPAA compliance engine logic adapted for v2.2 governance integration."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

ComplianceResult = Dict[str, Any]


HIPAA_BASELINE_REQUIRED_TYPES = ["vnet", "nsg", "keyvault", "privateendpoint", "loganalytics"]


HIPAA_CONTROLS: list[dict[str, Any]] = [
    {
        "control_id": "hipaa-encryption-at-rest",
        "title": "Encryption at Rest",
        "severity": "critical",
        "resource_types": ["storage", "sql", "sqlserver", "vm"],
        "description": "Data resources must enforce encryption at rest.",
        "remediation": "Enable encryption at rest or transparent data encryption on the resource.",
        "check": lambda resource, config: _is_enabled(config, "encryption_at_rest", "encryptionEnabled", "tde_enabled", "storage_encrypted", "disk_encryption"),
    },
    {
        "control_id": "hipaa-encryption-in-transit",
        "title": "Encryption in Transit",
        "severity": "high",
        "resource_types": ["storage", "sql", "sqlserver", "appservice", "gateway"],
        "description": "Network traffic to data and application services must be encrypted.",
        "remediation": "Enforce TLS 1.2+ and HTTPS-only traffic for the resource.",
        "check": lambda resource, config: _tls_or_transport_enforced(config),
    },
    {
        "control_id": "hipaa-private-endpoints",
        "title": "Private Endpoints",
        "severity": "high",
        "resource_types": ["storage", "sql", "sqlserver", "keyvault"],
        "description": "Sensitive services should avoid public endpoints.",
        "remediation": "Disable public access and enable private endpoints for the resource.",
        "check": lambda resource, config: _has_private_access_posture(config),
    },
    {
        "control_id": "hipaa-network-isolation",
        "title": "Network Isolation",
        "severity": "high",
        "resource_types": ["vm", "aks", "appservice", "container", "sql", "storage"],
        "description": "Resources must be integrated with private network controls.",
        "remediation": "Integrate resource with a vnet/subnet path and restrict public exposure.",
        "check": lambda resource, config: _has_network_isolation(config),
    },
    {
        "control_id": "hipaa-logging-monitoring",
        "title": "Logging and Monitoring",
        "severity": "high",
        "resource_types": ["vm", "sql", "storage", "nsg", "appservice", "keyvault", "gateway", "aks"],
        "description": "Audit logging and diagnostics should be enabled.",
        "remediation": "Enable diagnostics/logging and route logs to centralized monitoring.",
        "check": lambda resource, config: _has_logging_enabled(config),
    },
    {
        "control_id": "hipaa-backup-recovery",
        "title": "Backup and Recovery",
        "severity": "high",
        "resource_types": ["sql", "sqlserver", "storage"],
        "description": "Data services must have backup/recovery coverage.",
        "remediation": "Configure backup retention >= 30 days and geo-recovery protections.",
        "check": lambda resource, config: _has_backup_controls(config),
    },
    {
        "control_id": "hipaa-keyvault-protection",
        "title": "Key Vault Protection",
        "severity": "critical",
        "resource_types": ["keyvault"],
        "description": "Key Vault should enforce purge protection and soft delete.",
        "remediation": "Enable purge protection and soft delete retention in Key Vault.",
        "check": lambda resource, config: _is_enabled(config, "purge_protection", "purgeProtection") and _is_enabled(config, "soft_delete", "softDelete", "soft_delete_enabled"),
    },
    {
        "control_id": "hipaa-public-access-disabled",
        "title": "Public Access Disabled",
        "severity": "critical",
        "resource_types": ["storage", "sql", "sqlserver", "keyvault"],
        "description": "Public network access must be disabled for sensitive resources.",
        "remediation": "Disable public access and use private routing controls.",
        "check": lambda resource, config: _public_access_disabled(config),
    },
]


def validate_architecture(architecture_json: Dict[str, Any], frameworks: List[str] | None = None) -> ComplianceResult:
    architecture_json = architecture_json or {}
    target_frameworks = frameworks if frameworks is not None else _ensure_list(architecture_json.get("compliance"))
    normalized_frameworks = normalize_frameworks(target_frameworks)
    resources = list(_iter_resources(architecture_json))

    if "HIPAA" not in normalized_frameworks:
        return {
            "compliant": None,
            "overall_score": None,
            "frameworks": {},
            "violations": [],
            "recommendations": [],
            "controls": [],
            "findings": [],
            "summary": {"total_findings": 0, "critical_count": 0, "high_count": 0, "medium_count": 0, "low_count": 0},
            "message": "HIPAA must be selected to run compliance assessment.",
        }

    controls = _build_controls()
    findings: list[dict[str, Any]] = []

    present_types = {str(item.get("type") or "").strip().lower() for item in resources}
    for required in HIPAA_BASELINE_REQUIRED_TYPES:
        if required in present_types:
            continue
        findings.append(
            {
                "finding_id": f"hipaa-baseline-{required}",
                "framework": "HIPAA",
                "control_id": f"hipaa-baseline-{required}",
                "title": "HIPAA Baseline Control",
                "severity": "critical",
                "status": "fail",
                "message": f"Missing HIPAA baseline control resource type: {required}",
                "remediation": f"Add and configure at least one `{required}` resource in the architecture.",
                "resource_id": None,
                "resource_name": None,
                "resource_type": required,
            }
        )

    for resource in resources:
        resource_type = str(resource.get("type") or "").strip().lower()
        config = resource.get("configuration") if isinstance(resource.get("configuration"), dict) else {}
        for control in controls:
            if resource_type not in control["resource_types"]:
                continue
            try:
                passed = bool(control["check"](resource, config))
            except Exception:
                passed = False
            if passed:
                continue

            findings.append(
                {
                    "finding_id": f"{control['control_id']}-{resource.get('id') or resource.get('name') or len(findings)}",
                    "framework": "HIPAA",
                    "control_id": control["control_id"],
                    "title": control["title"],
                    "severity": control["severity"],
                    "status": "fail",
                    "message": f"{resource.get('name') or resource_type}: {control['description']}",
                    "remediation": control["remediation"],
                    "resource_id": str(resource.get("id") or "") or None,
                    "resource_name": str(resource.get("name") or "") or None,
                    "resource_type": resource_type,
                }
            )

    critical_count = sum(1 for item in findings if item.get("severity") == "critical")
    high_count = sum(1 for item in findings if item.get("severity") == "high")
    medium_count = sum(1 for item in findings if item.get("severity") == "medium")
    low_count = sum(1 for item in findings if item.get("severity") == "low")

    overall_score = _score(critical=critical_count, high=high_count, medium=medium_count, low=low_count)
    status = _status_from_score(overall_score)

    violations = _dedupe_preserve_order(
        [f"[HIPAA] {item.get('message')}" for item in findings if str(item.get("status") or "") == "fail"]
    )
    recommendations = _dedupe_preserve_order(
        [f"[HIPAA] {item.get('remediation')}" for item in findings if str(item.get("remediation") or "").strip()]
    )

    return {
        "compliant": len(findings) == 0,
        "overall_score": overall_score,
        "frameworks": {
            "HIPAA": {
                "framework": "HIPAA",
                "status": status,
                "score": overall_score,
                "critical_count": critical_count,
                "high_count": high_count,
                "medium_count": medium_count,
                "low_count": low_count,
            }
        },
        "violations": violations,
        "recommendations": recommendations,
        "controls": controls,
        "findings": findings,
        "summary": {
            "total_findings": len(findings),
            "critical_count": critical_count,
            "high_count": high_count,
            "medium_count": medium_count,
            "low_count": low_count,
        },
        "message": None,
    }


def normalize_frameworks(items: Iterable[str]) -> List[str]:
    normalized: list[str] = []
    for item in items:
        if not item:
            continue
        value = str(item).strip().lower()
        value = re.sub(r"[\s_]+", " ", value)
        if value in {"hipaa"}:
            normalized.append("HIPAA")
    return _dedupe_preserve_order(normalized)


def _build_controls() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in HIPAA_CONTROLS:
        rows.append(
            {
                "control_id": str(item["control_id"]),
                "title": str(item["title"]),
                "severity": str(item["severity"]),
                "resource_types": [str(v) for v in item.get("resource_types") or []],
                "description": str(item["description"]),
                "remediation": str(item["remediation"]),
                "check": item["check"],
            }
        )
    return rows


def _ensure_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        ordered.append(item)
        seen.add(item)
    return ordered


def _iter_resources(architecture_json: Dict[str, Any]):
    resources = architecture_json.get("resources")
    if isinstance(resources, list):
        for item in resources:
            if not isinstance(item, dict):
                continue
            yield {
                "id": str(item.get("id") or "") or None,
                "type": _normalize_resource_type(str(item.get("type") or item.get("resource_type") or "")),
                "name": str(item.get("name") or "").strip() or None,
                "configuration": item.get("configuration") if isinstance(item.get("configuration"), dict) else item.get("properties") if isinstance(item.get("properties"), dict) else {},
            }


def _normalize_resource_type(resource_type: str) -> str:
    normalized = (resource_type or "").strip().lower()
    aliases = {
        "azure-sql": "sql",
        "azure-storage": "storage",
        "azure-vm": "vm",
        "azure-keyvault": "keyvault",
        "azure-app-service": "appservice",
        "azure-appgw": "gateway",
    }
    return aliases.get(normalized, normalized)


def _normalize_boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "enabled", "on", "1"}:
            return True
        if lowered in {"false", "no", "disabled", "off", "0"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def _value(config: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in config:
            return config.get(key)
    return None


def _is_enabled(config: dict[str, Any], *keys: str) -> bool:
    val = _value(config, *keys)
    normalized = _normalize_boolean(val)
    return normalized is True


def _tls_or_transport_enforced(config: dict[str, Any]) -> bool:
    if _is_enabled(config, "encryption_in_transit", "https_only", "httpsOnly", "tls_enforced"):
        return True
    min_tls = _value(config, "min_tls_version", "minTlsVersion", "minimum_tls_version")
    if min_tls is None:
        return False
    try:
        return float(str(min_tls).replace("TLS", "").strip()) >= 1.2
    except Exception:
        return str(min_tls).strip() in {"1.2", "1.3", "TLS1_2", "TLS1_3"}


def _public_access_disabled(config: dict[str, Any]) -> bool:
    public_access = _value(config, "public_access", "publicAccess", "publicEndpoint")
    normalized = _normalize_boolean(public_access)
    if normalized is False:
        return True
    access_mode = str(_value(config, "network_access", "publicNetworkAccess", "networkAccess") or "").strip().lower()
    return access_mode in {"private", "private_only", "disabled", "deny"}


def _has_private_access_posture(config: dict[str, Any]) -> bool:
    if _is_enabled(config, "private_endpoint", "private_endpoints", "privateEndpoint", "privateEndpoints"):
        return True
    return _public_access_disabled(config)


def _has_network_isolation(config: dict[str, Any]) -> bool:
    if _is_enabled(config, "vnet_integration", "vnetIntegration", "private_networking", "network_isolation"):
        return True
    if _has_private_access_posture(config):
        return True
    subnet_id = _value(config, "subnet_id", "subnetId", "vnet_subnet")
    return bool(str(subnet_id or "").strip())


def _has_logging_enabled(config: dict[str, Any]) -> bool:
    if _is_enabled(config, "logging", "diagnostics", "diagnostic_logs_enabled", "audit_logging"):
        return True
    log_workspace = _value(config, "log_analytics_workspace", "logAnalyticsWorkspace", "monitoring_workspace")
    return bool(str(log_workspace or "").strip())


def _has_backup_controls(config: dict[str, Any]) -> bool:
    if _is_enabled(config, "geo_replication", "geoReplication", "backup_enabled", "backupEnabled"):
        return True
    value = _value(config, "backup_retention_days", "backupRetentionDays", "backup_retention")
    try:
        return int(value or 0) >= 30
    except Exception:
        return False


def _status_from_score(score: int) -> str:
    if score >= 90:
        return "compliant"
    if score >= 70:
        return "partial"
    return "non-compliant"


def _score(*, critical: int, high: int, medium: int, low: int) -> int:
    baseline = 100 - (critical * 20) - (high * 10) - (medium * 5) - (low * 2)
    return max(0, min(100, int(round(baseline))))
