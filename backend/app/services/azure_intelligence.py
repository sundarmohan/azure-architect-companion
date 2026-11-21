"""Deterministic Azure Resource Intelligence snapshots and preflight."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.config import Settings, settings
from ..enums import (
    AzureAvailabilityStatus,
    AzureConnectionStatus,
    AzureFreshnessStatus,
    AzurePreflightStatus,
    AzureProviderRegistrationStatus,
    AzureQuotaStatus,
    ValidationFindingSeverity,
)
from ..models import (
    Architecture,
    ArchitectureVersion,
    AzureConnection,
    AzureIntelligenceSnapshot,
    AzurePreflightResult,
    Resource,
)
from .azure_clients import AzureReadOnlyClient, AzureSdkReadOnlyClient
from .architecture_versioning import ArchitectureVersioningService
from .services import ValidationEngine


logger = logging.getLogger(__name__)


class AzureIntelligenceError(ValueError):
    """Safe application-level Azure failure."""

    def __init__(self, code: str, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class AzureResourceIntelligenceService:
    """Collect, normalize, persist, and evaluate read-only Azure evidence."""

    SOURCE_VERSION = "m10-v1"
    _locks_guard = threading.Lock()
    _locks: dict[str, threading.Lock] = {}
    _secret_fragments = (
        "password", "passwd", "secret", "token", "apikey", "api_key",
        "privatekey", "private_key", "connectionstring", "connection_string",
        "credential", "authorization",
    )

    @classmethod
    def connection_status(
        cls,
        config: Settings = settings,
        client: AzureReadOnlyClient | None = None,
    ) -> dict[str, Any]:
        if not config.azure_tenant_id or not config.azure_subscription_id:
            return {
                "status": AzureConnectionStatus.CONFIGURATION_ERROR.value,
                "tenant_id": config.azure_tenant_id,
                "subscription_id": config.azure_subscription_id,
                "message": "Azure tenant and subscription are not configured",
            }
        try:
            subscription = (client or AzureSdkReadOnlyClient(config)).get_subscription()
            return {
                "status": AzureConnectionStatus.CONNECTED.value,
                "tenant_id": config.azure_tenant_id,
                "subscription_id": config.azure_subscription_id,
                "subscription": cls._sanitize(subscription),
                "message": "Read-only Azure connection is available",
            }
        except Exception as error:
            normalized = cls.normalize_error(error)
            return {
                "status": cls._connection_status_for(normalized.code),
                "tenant_id": config.azure_tenant_id,
                "subscription_id": config.azure_subscription_id,
                "message": str(normalized),
                "error_code": normalized.code,
            }

    @classmethod
    def refresh(
        cls,
        db: Session,
        client: AzureReadOnlyClient | None = None,
        config: Settings = settings,
        regions: list[str] | None = None,
        terraform_provider_version: str | None = None,
        now: datetime | None = None,
    ) -> AzureIntelligenceSnapshot:
        if not config.azure_tenant_id or not config.azure_subscription_id:
            raise AzureIntelligenceError(
                "AZURE_ADAPTER_NOT_CONFIGURED",
                "Azure tenant and subscription are not configured",
                503,
            )
        retrieved_at = cls._utc(now)
        started_at = time.monotonic()
        scope_key = f"{config.azure_tenant_id}:{config.azure_subscription_id}"
        with cls._scope_lock(scope_key):
            connection = cls._get_or_create_connection(db, config)
            try:
                azure = client or cls._build_client(config)
                subscription = cls._sanitize(azure.get_subscription())
                azure_regions = cls._normalized_list(azure.list_locations())
                providers = cls._normalized_list(azure.list_providers())
                resource_types = cls._normalized_list(azure.list_resource_types())
                skus = cls._normalized_list(azure.list_skus())
                resource_groups = cls._normalized_list(azure.list_resource_groups())
                resources = cls._normalized_list(azure.list_resources())
                requested_regions = sorted(set(regions or cls._resource_regions(resources)))
                quotas = cls._normalized_list(azure.list_quotas(requested_regions))
            except Exception as error:
                normalized = cls.normalize_error(error)
                connection.status = cls._connection_status_for(normalized.code)
                connection.last_checked_at = retrieved_at
                db.commit()
                logger.warning(
                    "azure_intelligence_refresh status=failed subscription=%s code=%s correlation_id=%s duration_ms=%d",
                    config.azure_subscription_id,
                    normalized.code,
                    cls._correlation_id(error),
                    int((time.monotonic() - started_at) * 1000),
                )
                raise normalized from None

            connection.status = AzureConnectionStatus.CONNECTED.value
            connection.last_checked_at = retrieved_at
            if subscription.get("display_name"):
                connection.display_name = str(subscription["display_name"])
            sequence = (
                db.query(func.max(AzureIntelligenceSnapshot.snapshot_sequence))
                .filter(AzureIntelligenceSnapshot.connection_id == connection.id)
                .scalar()
                or 0
            ) + 1
            region_records = cls._regions(azure_regions, resource_types, skus, resources)
            payload = {
                "subscription": subscription,
                "resource_groups": resource_groups,
                "resource_types": resource_types,
                "regions": region_records,
                "skus": skus,
                "providers": providers,
                "quotas": quotas,
                "resources": resources,
                "source_version": cls.SOURCE_VERSION,
                "terraform_provider_version": terraform_provider_version,
            }
            snapshot = AzureIntelligenceSnapshot(
                connection_id=connection.id,
                subscription_id=config.azure_subscription_id,
                tenant_id=config.azure_tenant_id,
                snapshot_sequence=sequence,
                snapshot_hash=cls.stable_hash(payload),
                source_version=cls.SOURCE_VERSION,
                terraform_provider_version=terraform_provider_version,
                subscription_metadata=subscription,
                resource_groups=resource_groups,
                resource_types=resource_types,
                regions=region_records,
                skus=skus,
                providers=providers,
                quotas=quotas,
                resources=resources,
                retrieved_at=retrieved_at,
                expires_at=retrieved_at + timedelta(seconds=config.azure_intelligence_cache_ttl_seconds),
            )
            db.add(snapshot)
            db.commit()
            db.refresh(snapshot)
            logger.info(
                "azure_intelligence_refresh status=success subscription=%s snapshot=%s duration_ms=%d",
                config.azure_subscription_id,
                snapshot.id,
                int((time.monotonic() - started_at) * 1000),
            )
            return snapshot

    @classmethod
    def list_snapshots(cls, db: Session, config: Settings = settings) -> list[AzureIntelligenceSnapshot]:
        if not config.azure_tenant_id or not config.azure_subscription_id:
            return []
        return (
            db.query(AzureIntelligenceSnapshot)
            .filter(
                AzureIntelligenceSnapshot.tenant_id == config.azure_tenant_id,
                AzureIntelligenceSnapshot.subscription_id == config.azure_subscription_id,
            )
            .order_by(AzureIntelligenceSnapshot.snapshot_sequence.desc())
            .all()
        )

    @classmethod
    def get_snapshot(
        cls, db: Session, snapshot_id: UUID, config: Settings = settings
    ) -> AzureIntelligenceSnapshot | None:
        if not config.azure_tenant_id or not config.azure_subscription_id:
            return None
        return (
            db.query(AzureIntelligenceSnapshot)
            .filter(
                AzureIntelligenceSnapshot.id == snapshot_id,
                AzureIntelligenceSnapshot.tenant_id == config.azure_tenant_id,
                AzureIntelligenceSnapshot.subscription_id == config.azure_subscription_id,
            )
            .first()
        )

    @classmethod
    def latest_snapshot(cls, db: Session, config: Settings = settings) -> AzureIntelligenceSnapshot | None:
        items = cls.list_snapshots(db, config)
        return items[0] if items else None

    @classmethod
    def resource_type_intelligence(
        cls, snapshot: AzureIntelligenceSnapshot, resource_type: str, region: str | None = None
    ) -> dict[str, Any]:
        metadata = cls._resource_type(snapshot, resource_type)
        if not metadata:
            return cls._availability(
                AzureAvailabilityStatus.UNKNOWN.value, resource_type, region, None, "Resource type was not returned by Azure"
            )
        provider = str(metadata.get("provider_namespace") or resource_type.split("/", 1)[0])
        if region is None:
            status = AzureAvailabilityStatus.SUPPORTED.value
        else:
            region_result = cls.region_intelligence(snapshot, resource_type, region)
            status = region_result["status"]
        return cls._availability(
            status,
            resource_type,
            region,
            provider,
            "Azure Resource Manager resource type metadata",
            api_version=metadata.get("preferred_api_version"),
            api_versions=metadata.get("api_versions") or [],
            capabilities=metadata.get("capabilities") or {},
            restrictions=metadata.get("restrictions") or [],
        ) | cls.freshness(snapshot)

    @classmethod
    def region_intelligence(
        cls, snapshot: AzureIntelligenceSnapshot, resource_type: str, region: str
    ) -> dict[str, Any]:
        metadata = cls._resource_type(snapshot, resource_type)
        if not metadata:
            status = AzureAvailabilityStatus.UNKNOWN.value
            evidence = "Resource type metadata is unavailable"
        else:
            locations = metadata.get("locations") or []
            if not locations:
                status = AzureAvailabilityStatus.UNKNOWN.value
                evidence = "Azure did not publish locations for this resource type"
            elif cls._location_matches(region, locations, snapshot.regions or []):
                status = AzureAvailabilityStatus.SUPPORTED.value
                evidence = "Region appears in Azure Resource Manager metadata"
            else:
                status = AzureAvailabilityStatus.UNSUPPORTED.value
                evidence = "Region does not appear in Azure Resource Manager metadata"
        return cls._availability(status, resource_type, region, resource_type.split("/", 1)[0], evidence) | cls.freshness(snapshot)

    @classmethod
    def sku_intelligence(
        cls, snapshot: AzureIntelligenceSnapshot, resource_type: str, region: str, sku_name: str
    ) -> dict[str, Any]:
        candidates = [
            item for item in (snapshot.skus or [])
            if cls._same(item.get("resource_type"), resource_type) and cls._same(item.get("name"), sku_name)
        ]
        if not candidates:
            status = AzureAvailabilityStatus.UNKNOWN.value
            evidence = "Azure did not return this SKU for the resource type"
            selected: dict[str, Any] = {}
        else:
            selected = candidates[0]
            locations = selected.get("locations") or []
            restrictions = selected.get("restrictions") or []
            restricted = cls._region_restricted(region, restrictions)
            if restricted:
                status = AzureAvailabilityStatus.UNSUPPORTED.value
                evidence = "Azure SKU restrictions include the selected region"
            elif cls._location_matches(region, locations, snapshot.regions or []):
                status = AzureAvailabilityStatus.SUPPORTED.value
                evidence = "Azure Compute SKU metadata includes the selected region"
            else:
                status = AzureAvailabilityStatus.UNSUPPORTED.value
                evidence = "Azure Compute SKU metadata excludes the selected region"
        return cls._availability(
            status, resource_type, region, resource_type.split("/", 1)[0], evidence,
            sku=sku_name, tier=selected.get("tier"), capabilities=selected.get("capabilities") or {},
            restrictions=selected.get("restrictions") or [],
        ) | cls.freshness(snapshot)

    @classmethod
    def provider_intelligence(cls, snapshot: AzureIntelligenceSnapshot, namespace: str) -> dict[str, Any]:
        provider = next((item for item in (snapshot.providers or []) if cls._same(item.get("namespace"), namespace)), None)
        if not provider:
            status = AzureProviderRegistrationStatus.UNKNOWN.value
        elif str(provider.get("registration_state", "")).casefold() == "registered":
            status = AzureProviderRegistrationStatus.REGISTERED.value
        else:
            status = AzureProviderRegistrationStatus.NOT_REGISTERED.value
        return {
            "provider_namespace": namespace,
            "status": status,
            "source": "AZURE_RESOURCE_MANAGER",
            "retrieved_at": snapshot.retrieved_at,
        } | cls.freshness(snapshot)

    @classmethod
    def quota_intelligence(
        cls, snapshot: AzureIntelligenceSnapshot, quota_name: str, region: str, required: float
    ) -> dict[str, Any]:
        quota = next(
            (item for item in (snapshot.quotas or []) if cls._same(item.get("name"), quota_name) and cls._same(item.get("region"), region)),
            None,
        )
        usage = quota.get("current_usage") if quota else None
        limit = quota.get("limit") if quota else None
        if usage is None or limit is None:
            status = AzureQuotaStatus.UNKNOWN.value
            remaining = None
        else:
            remaining = float(limit) - float(usage)
            status = AzureQuotaStatus.AVAILABLE.value if remaining >= required else AzureQuotaStatus.INSUFFICIENT.value
        return {
            "quota_name": quota_name,
            "region": region,
            "status": status,
            "current_usage": usage,
            "quota": limit,
            "required_amount": required,
            "remaining_amount": remaining,
            "source": quota.get("source") if quota else "AZURE_QUOTA_UNAVAILABLE",
            "retrieved_at": snapshot.retrieved_at,
        } | cls.freshness(snapshot)

    @classmethod
    def preflight(
        cls,
        db: Session,
        architecture_id: UUID,
        version_id: UUID,
        snapshot_id: UUID | None = None,
        config: Settings = settings,
        now: datetime | None = None,
    ) -> AzurePreflightResult:
        architecture = db.query(Architecture).filter(Architecture.id == architecture_id).first()
        version = db.query(ArchitectureVersion).filter(
            ArchitectureVersion.id == version_id,
            ArchitectureVersion.architecture_id == architecture_id,
        ).first()
        if not architecture or not version:
            raise AzureIntelligenceError("ARCHITECTURE_VERSION_NOT_FOUND", "Architecture version not found", 404)
        snapshot = cls.get_snapshot(db, snapshot_id, config) if snapshot_id else cls.latest_snapshot(db, config)
        if not snapshot:
            raise AzureIntelligenceError("AZURE_SNAPSHOT_NOT_FOUND", "No Azure intelligence snapshot is available", 404)

        findings: list[dict[str, Any]] = []
        static_validation = ValidationEngine.validate_version(db, architecture_id, version_id)
        for finding in static_validation["findings"]:
            findings.append({
                "code": f"STATIC_{finding['code']}",
                "severity": finding["severity"],
                "message": finding["message"],
                "resource_id": str(finding["resource_id"]) if finding.get("resource_id") else None,
                "resource_key": None,
                "details": cls._sanitize({"category": finding["category"], **(finding.get("details") or {})}),
            })
        if cls.freshness(snapshot, now)["freshness"] == AzureFreshnessStatus.STALE.value:
            findings.append(cls._finding("AZURE_DATA_STALE", ValidationFindingSeverity.WARNING.value, "Azure availability data is stale", None, {"snapshot_id": str(snapshot.id), "expires_at": snapshot.expires_at.isoformat()}))

        resources = db.query(Resource).filter(Resource.architecture_version_id == version_id).order_by(Resource.resource_key).all()
        for resource in resources:
            provider = resource.resource_type.split("/", 1)[0] if "/" in resource.resource_type else None
            if not provider:
                findings.append(cls._finding("AZURE_RESOURCE_TYPE_UNKNOWN", ValidationFindingSeverity.WARNING.value, "Azure provider namespace could not be established", resource, {"status": "UNKNOWN"}))
                continue
            provider_result = cls.provider_intelligence(snapshot, provider)
            if provider_result["status"] == AzureProviderRegistrationStatus.NOT_REGISTERED.value:
                findings.append(cls._finding("AZURE_PROVIDER_NOT_REGISTERED", ValidationFindingSeverity.ERROR.value, f"Required provider {provider} is not registered", resource, provider_result))
            elif provider_result["status"] == AzureProviderRegistrationStatus.UNKNOWN.value:
                findings.append(cls._finding("AZURE_PROVIDER_UNKNOWN", ValidationFindingSeverity.WARNING.value, f"Registration for provider {provider} is unknown", resource, provider_result))

            type_result = cls.resource_type_intelligence(snapshot, resource.resource_type, resource.location)
            if type_result["status"] in {AzureAvailabilityStatus.UNSUPPORTED.value, AzureAvailabilityStatus.UNAVAILABLE.value}:
                findings.append(cls._finding("AZURE_RESOURCE_UNAVAILABLE", ValidationFindingSeverity.ERROR.value, "Resource type is unavailable in the selected region", resource, type_result))
            elif type_result["status"] == AzureAvailabilityStatus.UNKNOWN.value:
                findings.append(cls._finding("AZURE_RESOURCE_AVAILABILITY_UNKNOWN", ValidationFindingSeverity.WARNING.value, "Resource type availability is unknown", resource, type_result))

            sku_name = (resource.sku or {}).get("name") if isinstance(resource.sku, dict) else None
            if sku_name and resource.location:
                sku_result = cls.sku_intelligence(snapshot, resource.resource_type, resource.location, str(sku_name))
                if sku_result["status"] == AzureAvailabilityStatus.UNSUPPORTED.value:
                    findings.append(cls._finding("AZURE_SKU_UNAVAILABLE", ValidationFindingSeverity.ERROR.value, "Selected SKU is unavailable in the selected region", resource, sku_result))
                elif sku_result["status"] == AzureAvailabilityStatus.UNKNOWN.value:
                    findings.append(cls._finding("AZURE_SKU_AVAILABILITY_UNKNOWN", ValidationFindingSeverity.WARNING.value, "Selected SKU availability is unknown", resource, sku_result))

                requirements = (resource.properties or {}).get("required_capabilities", {})
                if isinstance(requirements, dict):
                    actual_capabilities = sku_result.get("capabilities") or {}
                    for capability, required_value in sorted(requirements.items()):
                        actual_value = actual_capabilities.get(capability)
                        if actual_value is None:
                            findings.append(cls._finding("AZURE_CAPABILITY_UNKNOWN", ValidationFindingSeverity.WARNING.value, f"Capability {capability} is unknown", resource, {"status": "UNKNOWN", "capability": capability, "required": required_value}))
                        elif str(actual_value).casefold() != str(required_value).casefold():
                            findings.append(cls._finding("AZURE_CAPABILITY_UNSUPPORTED", ValidationFindingSeverity.ERROR.value, f"Selected SKU does not satisfy capability {capability}", resource, {"status": "UNSUPPORTED", "capability": capability, "required": required_value, "actual": actual_value}))

            for quota_requirement in (resource.properties or {}).get("required_quotas", []):
                if not isinstance(quota_requirement, dict) or not resource.location:
                    continue
                name = quota_requirement.get("name")
                amount = quota_requirement.get("amount")
                if not name or not isinstance(amount, (int, float)):
                    continue
                quota_result = cls.quota_intelligence(snapshot, str(name), resource.location, float(amount))
                severity = ValidationFindingSeverity.ERROR.value if quota_result["status"] == AzureQuotaStatus.INSUFFICIENT.value else ValidationFindingSeverity.WARNING.value
                if quota_result["status"] != AzureQuotaStatus.AVAILABLE.value:
                    findings.append(cls._finding(f"AZURE_QUOTA_{quota_result['status']}", severity, f"Quota {name} is {quota_result['status'].lower()}", resource, quota_result))

        if any(item["severity"] == ValidationFindingSeverity.ERROR.value for item in findings):
            result_status = AzurePreflightStatus.FAILED.value
        elif any((item.get("details") or {}).get("status") == "UNKNOWN" or item["code"].endswith("UNKNOWN") or item["code"] == "AZURE_DATA_STALE" for item in findings):
            result_status = AzurePreflightStatus.UNKNOWN.value
        else:
            result_status = AzurePreflightStatus.PASSED.value
        payload = {
            "architecture_id": str(architecture_id),
            "architecture_version_id": str(version_id),
            "azure_snapshot_id": str(snapshot.id),
            "status": result_status,
            "findings": findings,
        }
        architecture_snapshot_hash = ArchitectureVersioningService.snapshot_hash(db, architecture_id, version_id)
        payload["architecture_snapshot_hash"] = architecture_snapshot_hash
        result = AzurePreflightResult(
            architecture_id=architecture_id,
            architecture_version_id=version_id,
            azure_snapshot_id=snapshot.id,
            architecture_snapshot_hash=architecture_snapshot_hash,
            status=result_status,
            findings=findings,
            result_hash=cls.stable_hash(payload),
        )
        db.add(result)
        db.commit()
        db.refresh(result)
        return result

    @staticmethod
    def freshness(snapshot: AzureIntelligenceSnapshot, now: datetime | None = None) -> dict[str, Any]:
        current = AzureResourceIntelligenceService._utc(now)
        expires_at = AzureResourceIntelligenceService._utc(snapshot.expires_at)
        fresh = current < expires_at
        return {
            "fresh": fresh,
            "freshness": AzureFreshnessStatus.FRESH.value if fresh else AzureFreshnessStatus.STALE.value,
            "retrieved_at": snapshot.retrieved_at,
            "expires_at": snapshot.expires_at,
        }

    @staticmethod
    def stable_hash(payload: Any) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def normalize_error(cls, error: Exception) -> AzureIntelligenceError:
        if isinstance(error, AzureIntelligenceError):
            return error
        name = type(error).__name__.casefold()
        status_code = getattr(error, "status_code", None)
        if isinstance(error, ValueError):
            return AzureIntelligenceError("AZURE_ADAPTER_NOT_CONFIGURED", "Azure connection configuration is invalid", 503)
        if "authentication" in name or status_code == 401:
            return AzureIntelligenceError("AZURE_AUTHENTICATION_FAILED", "Azure authentication failed", 401)
        if "authorization" in name or "forbidden" in name or status_code == 403:
            return AzureIntelligenceError("AZURE_AUTHORIZATION_FAILED", "Azure authorization failed", 403)
        if "timeout" in name:
            return AzureIntelligenceError("AZURE_TIMEOUT", "Azure request timed out", 504)
        if status_code == 404:
            return AzureIntelligenceError("AZURE_RESOURCE_NOT_FOUND", "Azure resource was not found", 404)
        if status_code == 429:
            return AzureIntelligenceError("AZURE_RATE_LIMITED", "Azure request was rate limited", 503)
        if isinstance(error, (ConnectionError, RuntimeError)):
            return AzureIntelligenceError("AZURE_API_UNAVAILABLE", "Azure API is unavailable", 503)
        return AzureIntelligenceError("AZURE_UNKNOWN_ERROR", "Azure request failed", 503)

    @classmethod
    def _get_or_create_connection(cls, db: Session, config: Settings) -> AzureConnection:
        connection = db.query(AzureConnection).filter(
            AzureConnection.tenant_id == config.azure_tenant_id,
            AzureConnection.subscription_id == config.azure_subscription_id,
        ).with_for_update().first()
        if connection:
            return connection
        connection = AzureConnection(
            tenant_id=config.azure_tenant_id,
            subscription_id=config.azure_subscription_id,
            credential_mode=config.azure_credential_mode,
        )
        db.add(connection)
        db.flush()
        return connection

    @classmethod
    def _scope_lock(cls, key: str) -> threading.Lock:
        with cls._locks_guard:
            return cls._locks.setdefault(key, threading.Lock())

    @staticmethod
    def _build_client(config: Settings) -> AzureReadOnlyClient:
        try:
            return AzureSdkReadOnlyClient(config)
        except Exception as error:
            raise AzureResourceIntelligenceService.normalize_error(error) from None

    @classmethod
    def _sanitize(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): cls._sanitize(item)
                for key, item in value.items()
                if not any(fragment in str(key).casefold().replace("-", "_") for fragment in cls._secret_fragments)
            }
        if isinstance(value, list):
            return [cls._sanitize(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    @classmethod
    def _normalized_list(cls, values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sanitized = [cls._sanitize(item) for item in values]
        return sorted(sanitized, key=lambda item: json.dumps(item, sort_keys=True, default=str))

    @staticmethod
    def _same(left: Any, right: Any) -> bool:
        return isinstance(left, str) and isinstance(right, str) and left.casefold() == right.casefold()

    @classmethod
    def _resource_type(cls, snapshot: AzureIntelligenceSnapshot, resource_type: str) -> dict[str, Any] | None:
        return next((item for item in (snapshot.resource_types or []) if cls._same(item.get("resource_type"), resource_type)), None)

    @classmethod
    def _location_matches(cls, requested: str, locations: list[Any], aliases: list[dict[str, Any]]) -> bool:
        candidates = {str(item).casefold() for item in locations if item}
        for alias in aliases:
            values = {alias.get("name"), alias.get("display_name"), *(alias.get("aliases") or [])}
            if any(isinstance(value, str) and value.casefold() == requested.casefold() for value in values):
                candidates.update(str(value).casefold() for value in values if value)
        return requested.casefold() in candidates

    @classmethod
    def _region_restricted(cls, region: str, restrictions: list[dict[str, Any]]) -> bool:
        return any(
            cls._location_matches(region, item.get("values") or [], [])
            for item in restrictions
            if str(item.get("type", "")).casefold() == "location"
        )

    @classmethod
    def _regions(cls, azure_regions: list[dict[str, Any]], resource_types: list[dict[str, Any]], skus: list[dict[str, Any]], resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        names = set(cls._resource_regions(resources))
        for item in resource_types + skus:
            names.update(str(location) for location in (item.get("locations") or []) if location)
        records = {str(item.get("name")): item for item in azure_regions if item.get("name")}
        known_values = {
            str(value).casefold()
            for item in azure_regions
            for value in (item.get("name"), item.get("display_name"), item.get("regional_display_name"))
            if value
        }
        for name in names:
            if name.casefold() not in known_values:
                records[name] = {"name": name, "display_name": name, "aliases": []}
        return sorted(records.values(), key=lambda item: str(item.get("name", "")).casefold())

    @staticmethod
    def _resource_regions(resources: list[dict[str, Any]]) -> list[str]:
        return sorted({str(item["location"]) for item in resources if item.get("location")}, key=str.casefold)

    @staticmethod
    def _availability(status: str, resource_type: str, region: str | None, provider: str | None, evidence: str, **details: Any) -> dict[str, Any]:
        return {
            "status": status,
            "resource_type": resource_type,
            "region": region,
            "provider_namespace": provider,
            "evidence": evidence,
            "source": details.pop("source", "AZURE_RESOURCE_INTELLIGENCE_SNAPSHOT"),
            **details,
        }

    @staticmethod
    def _finding(code: str, severity: str, message: str, resource: Resource | None, details: dict[str, Any]) -> dict[str, Any]:
        return {
            "code": code,
            "severity": severity,
            "message": message,
            "resource_id": str(resource.id) if resource else None,
            "resource_key": resource.resource_key if resource else None,
            "details": AzureResourceIntelligenceService._sanitize(details),
        }

    @staticmethod
    def _connection_status_for(code: str) -> str:
        return {
            "AZURE_AUTHENTICATION_FAILED": AzureConnectionStatus.AUTHENTICATION_FAILED.value,
            "AZURE_AUTHORIZATION_FAILED": AzureConnectionStatus.AUTHORIZATION_FAILED.value,
            "AZURE_TIMEOUT": AzureConnectionStatus.TIMEOUT.value,
            "AZURE_ADAPTER_NOT_CONFIGURED": AzureConnectionStatus.CONFIGURATION_ERROR.value,
        }.get(code, AzureConnectionStatus.UNAVAILABLE.value)

    @staticmethod
    def _correlation_id(error: Exception) -> str | None:
        response = getattr(error, "response", None)
        headers = getattr(response, "headers", {}) or {}
        return headers.get("x-ms-correlation-request-id") or headers.get("x-ms-request-id")

    @staticmethod
    def _utc(value: datetime | None) -> datetime:
        current = value or datetime.now(timezone.utc)
        return current.replace(tzinfo=timezone.utc) if current.tzinfo is None else current.astimezone(timezone.utc)
