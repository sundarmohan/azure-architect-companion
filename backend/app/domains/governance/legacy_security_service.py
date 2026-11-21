"""Reused legacy architecture security assessment logic adapted for V2.11."""

from __future__ import annotations

from typing import Any


def scan_architecture_security(architecture: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    resources = architecture.get("resources", [])
    connections = architecture.get("connections", [])

    for resource in resources:
        resource_type = resource.get("resource_type", "")
        resource_name = resource.get("name", "")

        if resource.get("network_access") == "public":
            findings.append(
                {
                    "id": f"public-access-{resource_name}",
                    "resource_id": resource.get("id"),
                    "resource_name": resource_name,
                    "resource_type": resource_type,
                    "severity": "high",
                    "title": "Public Network Access",
                    "description": f"Resource {resource_name} has public network access",
                    "recommendation": "Use private endpoints or service endpoints instead of public access",
                    "category": "network_security",
                }
            )

        if not resource.get("encryption_at_rest", False):
            if resource_type in ["azure-sql", "azure-postgres", "azure-blob", "azure-disk"]:
                findings.append(
                    {
                        "id": f"no-encryption-rest-{resource_name}",
                        "resource_id": resource.get("id"),
                        "resource_name": resource_name,
                        "resource_type": resource_type,
                        "severity": "high",
                        "title": "Missing Encryption at Rest",
                        "description": f"Resource {resource_name} does not have encryption at rest enabled",
                        "recommendation": "Enable encryption at rest for sensitive data",
                        "category": "data_protection",
                    }
                )

        if not resource.get("managed_identity", False):
            if resource_type in ["azure-app", "azure-func", "azure-aks"]:
                findings.append(
                    {
                        "id": f"no-managed-identity-{resource_name}",
                        "resource_id": resource.get("id"),
                        "resource_name": resource_name,
                        "resource_type": resource_type,
                        "severity": "medium",
                        "title": "Missing Managed Identity",
                        "description": f"Resource {resource_name} does not use managed identity",
                        "recommendation": "Use managed identity for authentication instead of secrets",
                        "category": "identity_management",
                    }
                )

        if not resource.get("nsg_applied", False):
            if resource_type not in ["azure-vnet", "azure-subnet"]:
                findings.append(
                    {
                        "id": f"no-nsg-{resource_name}",
                        "resource_id": resource.get("id"),
                        "resource_name": resource_name,
                        "resource_type": resource_type,
                        "severity": "medium",
                        "title": "Missing Network Security Group",
                        "description": f"Resource {resource_name} does not have NSG applied",
                        "recommendation": "Apply network security groups to restrict traffic",
                        "category": "network_security",
                    }
                )

    for connection in connections:
        if not connection.get("is_encrypted", False):
            findings.append(
                {
                    "id": f"unencrypted-connection-{connection.get('id')}",
                    "resource_id": connection.get("source_id"),
                    "resource_name": f"Connection from {connection.get('source_name', 'unknown')}",
                    "resource_type": "connection",
                    "severity": "high",
                    "title": "Unencrypted Connection",
                    "description": "Connection between resources is not encrypted",
                    "recommendation": "Use TLS/SSL encryption for all connections",
                    "category": "data_protection",
                }
            )

    return findings


def detect_secrets_in_architecture(architecture: dict[str, Any]) -> list[dict[str, Any]]:
    secrets: list[dict[str, Any]] = []
    resources = architecture.get("resources", [])

    for resource in resources:
        resource_name = resource.get("name", "")
        resource_type = resource.get("resource_type", "")
        config = resource.get("configuration", {})

        secret_patterns = [
            ("password", "Password detected in configuration"),
            ("secret", "Secret key detected in configuration"),
            ("key", "API key detected in configuration"),
            ("token", "Token detected in configuration"),
            ("credential", "Credential detected in configuration"),
        ]

        for key, value in config.items():
            if isinstance(value, str):
                for pattern, description in secret_patterns:
                    if pattern.lower() in key.lower() and len(value) > 10:
                        secrets.append(
                            {
                                "id": f"secret-{resource_name}-{key}",
                                "resource_id": resource.get("id"),
                                "resource_name": resource_name,
                                "resource_type": resource_type,
                                "type": pattern,
                                "location": f"configuration.{key}",
                                "description": description,
                                "severity": "critical",
                            }
                        )

    return secrets


def calculate_risk_levels(findings: list[dict[str, Any]], architecture: dict[str, Any]) -> dict[str, Any]:
    resources = architecture.get("resources", [])
    total_resources = len(resources)

    if total_resources == 0:
        return {"overall": "low", "score": 100}

    critical_weight = 10
    high_weight = 5
    medium_weight = 2
    low_weight = 1

    total_risk_score = 0
    max_possible_score = total_resources * critical_weight * 2

    for finding in findings:
        severity = finding.get("severity", "low")
        if severity == "critical":
            total_risk_score += critical_weight
        elif severity == "high":
            total_risk_score += high_weight
        elif severity == "medium":
            total_risk_score += medium_weight
        elif severity == "low":
            total_risk_score += low_weight

    risk_percentage = min(100, (total_risk_score / max_possible_score) * 100)
    security_score = max(0, 100 - risk_percentage)

    if security_score >= 90:
        overall_risk = "low"
    elif security_score >= 70:
        overall_risk = "medium"
    elif security_score >= 50:
        overall_risk = "high"
    else:
        overall_risk = "critical"

    return {
        "overall": overall_risk,
        "score": round(security_score, 1),
        "total_resources": total_resources,
        "findings_count": len(findings),
    }
