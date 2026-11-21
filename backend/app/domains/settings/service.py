from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import httpx
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.architecture.models import Architecture, ArchitectureRelationship, ArchitectureResource, AzureResourceGroup, AzureSubscription
from app.domains.cost.service import CostEstimationService
from app.domains.governance import GovernanceComplianceAdapter, GovernanceSecurityAdapter
from app.domains.incidents.models import MonitoringAlert
from app.domains.architecture.azure_discovery import ClientSecretCredential
from app.domains.settings.models import ProviderConfiguration
from .schemas import (
    AzureCredentialsWrite,
    AzureIntegrationStatusRead,
    AzureSubscriptionInventoryRead,
    CloudAccountCredentialsWrite,
    CloudAccountStatusRead,
    ProviderConnectionTestRead,
    ProviderStatusRead,
    SettingsOverviewRead,
)


_SUPPORTED_PROVIDERS = ("openai", "gemini")
_SUPPORTED_CLOUD_PROVIDERS = ("azure", "aws", "gcp")
_AZURE_PROVIDER_KEY = "azure_credentials"
_AWS_PROVIDER_KEY = "aws_credentials"
_GCP_PROVIDER_KEY = "gcp_credentials"
_CLOUD_PROVIDER_KEYS = {
    "azure": _AZURE_PROVIDER_KEY,
    "aws": _AWS_PROVIDER_KEY,
    "gcp": _GCP_PROVIDER_KEY,
}
_PROVIDER_ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}
_AZURE_ENV_KEYS = {
    "tenant_id": "AZURE_TENANT_ID",
    "client_id": "AZURE_CLIENT_ID",
    "client_secret": "AZURE_CLIENT_SECRET",
    "subscription_id": "AZURE_SUBSCRIPTION_ID",
}
_AWS_ENV_KEYS = {
    "access_key_id": "AWS_ACCESS_KEY_ID",
    "secret_access_key": "AWS_SECRET_ACCESS_KEY",
    "region": "AWS_DEFAULT_REGION",
}
_GCP_ENV_KEYS = {
    "service_account_json": "GCP_SERVICE_ACCOUNT_JSON",
}


@dataclass
class _ConnectionSnapshot:
    state: str = "unavailable"
    message: str | None = None
    authenticated_tenant_id: str | None = None
    authenticated_subscription_id: str | None = None
    authenticated_subscription_name: str | None = None
    authenticated_subscription_state: str | None = None
    last_tested_at: str | None = None


@dataclass
class _CloudAccountSnapshot:
    state: str = "unavailable"
    message: str | None = None
    authenticated_identity: str | None = None
    authenticated_name: str | None = None
    last_tested_at: str | None = None


class SettingsService:
    _runtime_secrets: dict[str, str] = {}
    _azure_runtime_credentials: dict[str, str] = {}
    _provider_connection: dict[str, _ConnectionSnapshot] = {
        "openai": _ConnectionSnapshot(),
        "gemini": _ConnectionSnapshot(),
    }
    _azure_connection: _ConnectionSnapshot = _ConnectionSnapshot()
    _aws_runtime_credentials: dict[str, str] = {}
    _gcp_runtime_credentials: dict[str, str] = {}
    _cloud_account_connection: dict[str, _CloudAccountSnapshot] = {
        "aws": _CloudAccountSnapshot(),
        "gcp": _CloudAccountSnapshot(),
    }

    @classmethod
    def reset_runtime_state(cls) -> None:
        cls._runtime_secrets = {}
        cls._azure_runtime_credentials = {}
        cls._provider_connection = {
            "openai": _ConnectionSnapshot(),
            "gemini": _ConnectionSnapshot(),
        }
        cls._azure_connection = _ConnectionSnapshot()
        cls._aws_runtime_credentials = {}
        cls._gcp_runtime_credentials = {}
        cls._cloud_account_connection = {
            "aws": _CloudAccountSnapshot(),
            "gcp": _CloudAccountSnapshot(),
        }

    def list_supported_cloud_providers(self) -> tuple[str, ...]:
        return _SUPPORTED_CLOUD_PROVIDERS

    def is_supported_cloud_provider(self, provider: str) -> bool:
        return provider in _SUPPORTED_CLOUD_PROVIDERS

    def list_supported_providers(self) -> tuple[str, ...]:
        return _SUPPORTED_PROVIDERS

    def is_supported_provider(self, provider: str) -> bool:
        return provider in _SUPPORTED_PROVIDERS

    @staticmethod
    def _now_utc_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def _set_azure_connection_snapshot(cls, snapshot: _ConnectionSnapshot) -> None:
        cls._azure_connection = snapshot

    @staticmethod
    def _azure_error_message_from_response(response: httpx.Response) -> str | None:
        try:
            payload = response.json()
        except Exception:
            return None

        if isinstance(payload, dict):
            error_value = payload.get("error")
            if isinstance(error_value, dict):
                code = str(error_value.get("code") or "").strip()
                message = str(error_value.get("message") or "").strip()
                if code and message:
                    return f"{code}: {message}"
                if message:
                    return message
            if isinstance(error_value, str):
                return error_value.strip() or None

            message = str(payload.get("message") or "").strip()
            if message:
                return message

        return None

    @staticmethod
    def _mask_client_id(client_id: str) -> str | None:
        value = (client_id or "").strip()
        if not value:
            return None
        if len(value) <= 8:
            return "*" * len(value)
        return f"{value[:4]}...{value[-4:]}"

    async def get_provider_secret(self, provider: str, db: AsyncSession | None = None) -> str:
        return await self._get_provider_key(provider, db=db)

    async def save_provider_key(self, provider: str, api_key: str, db: AsyncSession | None = None) -> ProviderStatusRead:
        value = (api_key or "").strip()
        if value:
            self._runtime_secrets[provider] = value
        else:
            self._runtime_secrets.pop(provider, None)

        if db is not None:
            row = await db.scalar(select(ProviderConfiguration).where(ProviderConfiguration.provider == provider))
            if row is None:
                row = ProviderConfiguration(provider=provider, api_key=value or None)
                db.add(row)
            else:
                row.api_key = value or None
            await db.commit()

        self._provider_connection[provider] = _ConnectionSnapshot()
        return await self._provider_status(provider, db=db)

    async def clear_provider_key(self, provider: str, db: AsyncSession | None = None) -> ProviderStatusRead:
        self._runtime_secrets.pop(provider, None)

        if db is not None:
            row = await db.scalar(select(ProviderConfiguration).where(ProviderConfiguration.provider == provider))
            if row is not None:
                row.api_key = None
                await db.commit()

        self._provider_connection[provider] = _ConnectionSnapshot(state="not_configured", message="Provider key is not configured.")
        return await self._provider_status(provider, db=db)

    async def get_settings_overview(self, db: AsyncSession | None = None) -> SettingsOverviewRead:
        azure_status = await self.get_azure_status(db=db)
        cloud_accounts = await self.get_cloud_accounts(db=db)
        providers = [await self._provider_status(name, db=db) for name in _SUPPORTED_PROVIDERS]
        return SettingsOverviewRead(ai_providers=providers, azure_integration=azure_status, cloud_accounts=cloud_accounts)

    async def list_azure_subscription_inventory(self, db: AsyncSession | None = None) -> list[AzureSubscriptionInventoryRead]:
        if db is None:
            return []

        azure_status = await self.get_azure_status(db=db)

        architecture_rows = await db.execute(select(Architecture).order_by(Architecture.created_at.desc()))
        architectures = list(architecture_rows.scalars().all())
        if not architectures:
            return []

        architecture_ids = [item.id for item in architectures]

        subscriptions_rows = await db.execute(
            select(AzureSubscription)
            .where(AzureSubscription.architecture_id.in_(architecture_ids))
            .order_by(AzureSubscription.created_at.desc())
        )
        subscriptions = list(subscriptions_rows.scalars().all())
        if not subscriptions:
            return []

        groups_rows = await db.execute(
            select(AzureResourceGroup)
            .where(AzureResourceGroup.architecture_id.in_(architecture_ids))
            .order_by(AzureResourceGroup.created_at.asc())
        )
        groups = list(groups_rows.scalars().all())

        resources_rows = await db.execute(
            select(ArchitectureResource)
            .where(ArchitectureResource.architecture_id.in_(architecture_ids))
            .order_by(ArchitectureResource.created_at.asc())
        )
        resources = list(resources_rows.scalars().all())

        relationships_rows = await db.execute(
            select(ArchitectureRelationship)
            .where(ArchitectureRelationship.architecture_id.in_(architecture_ids))
        )
        relationships = list(relationships_rows.scalars().all())

        alerts_rows = await db.execute(
            select(MonitoringAlert).where(MonitoringAlert.architecture_id.in_(architecture_ids))
        )
        alerts = list(alerts_rows.scalars().all())

        architecture_map = {item.id: item for item in architectures}
        groups_by_arch: dict[Any, list[AzureResourceGroup]] = {}
        resources_by_arch: dict[Any, list[ArchitectureResource]] = {}
        relationships_by_arch: dict[Any, list[ArchitectureRelationship]] = {}
        alerts_by_arch: dict[Any, list[MonitoringAlert]] = {}

        for item in groups:
            groups_by_arch.setdefault(item.architecture_id, []).append(item)
        for item in resources:
            resources_by_arch.setdefault(item.architecture_id, []).append(item)
        for item in relationships:
            relationships_by_arch.setdefault(item.architecture_id, []).append(item)
        for item in alerts:
            alerts_by_arch.setdefault(item.architecture_id, []).append(item)

        compliance_adapter = GovernanceComplianceAdapter()
        security_adapter = GovernanceSecurityAdapter()
        cost_service = CostEstimationService()

        items: list[AzureSubscriptionInventoryRead] = []

        for subscription in subscriptions:
            architecture = architecture_map.get(subscription.architecture_id)
            if not architecture:
                continue

            architecture_groups = groups_by_arch.get(architecture.id, [])
            architecture_resources = resources_by_arch.get(architecture.id, [])
            architecture_relationships = relationships_by_arch.get(architecture.id, [])
            architecture_alerts = alerts_by_arch.get(architecture.id, [])

            scoped_groups = [group for group in architecture_groups if group.subscription_id == subscription.id]
            group_id_set = {group.id for group in scoped_groups}
            external_subscription_id = str(subscription.subscription_id or "").strip().lower()

            scoped_resources: list[ArchitectureResource] = []
            scoped_resource_ids: set[Any] = set()
            for resource in architecture_resources:
                if resource.resource_group_id and resource.resource_group_id in group_id_set:
                    scoped_resources.append(resource)
                    scoped_resource_ids.add(resource.id)
                    continue

                props = resource.properties if isinstance(resource.properties, dict) else {}
                resource_subscription = str(props.get("azure_subscription_id") or "").strip().lower()
                if external_subscription_id and resource_subscription == external_subscription_id:
                    scoped_resources.append(resource)
                    scoped_resource_ids.add(resource.id)

            scoped_relationships = [
                rel
                for rel in architecture_relationships
                if rel.source_resource_id in scoped_resource_ids and rel.target_resource_id in scoped_resource_ids
            ]

            active_alerts = [
                alert
                for alert in architecture_alerts
                if alert.subscription_id == subscription.id and alert.status in {"open", "acknowledged", "investigating"}
            ]

            live_resources = sum(
                1
                for alert in active_alerts
                if str(alert.signal_state or "").lower() == "live"
            )
            has_error_signals = any(
                str(alert.signal_state or "").lower() in {"authentication_failure", "permission_failure", "azure_api_failure"}
                for alert in active_alerts
            )

            monitoring = SimpleNamespace(
                state=(
                    "azure_api_failure"
                    if has_error_signals
                    else ("live" if live_resources > 0 else ("no_data" if scoped_resources else "unsupported"))
                ),
                monitored_resources=len(scoped_resources),
                live_resources=live_resources,
            )

            unused = SimpleNamespace(total_unused=0, estimated_monthly_waste=0.0)

            compliance = compliance_adapter.build_summary(
                architecture_id=str(architecture.id),
                resources=scoped_resources,
                frameworks=["HIPAA"],
                default_region=architecture.default_region,
                azure_connection_state=azure_status.connection_state,
                azure_connection_message=azure_status.message,
            )

            security = security_adapter.build_summary(
                architecture_id=str(architecture.id),
                resources=scoped_resources,
                relationships=scoped_relationships,
            )

            estimate = await cost_service.estimate_architecture_cost(
                architecture=architecture,
                resources=scoped_resources,
                resource_groups=scoped_groups,
                subscriptions=[subscription],
                region_override=architecture.default_region,
            )

            active_incidents = {
                str(alert.incident_id)
                for alert in active_alerts
                if alert.incident_id is not None
            }

            last_discovery_sync = self._latest_discovery_sync(groups=scoped_groups, resources=scoped_resources)
            source_context = "discovered" if last_discovery_sync else "designed"

            items.append(
                AzureSubscriptionInventoryRead(
                    architecture_id=str(architecture.id),
                    architecture_name=architecture.name,
                    architecture_status=architecture.status,
                    subscription_db_id=str(subscription.id),
                    subscription_name=subscription.name,
                    subscription_id=subscription.subscription_id,
                    tenant_id=subscription.tenant_id,
                    connection_state=azure_status.connection_state,
                    authentication_state=azure_status.connection_state,
                    resource_group_count=len(scoped_groups),
                    resource_count=len(scoped_resources),
                    monitored_resource_count=monitoring.monitored_resources,
                    live_resource_count=monitoring.live_resources,
                    monitoring_state=monitoring.state,
                    active_alert_count=len(active_alerts),
                    active_incident_count=len(active_incidents),
                    unused_resource_count=unused.total_unused,
                    estimated_monthly_waste=unused.estimated_monthly_waste,
                    estimated_monthly_cost=estimate.total_monthly_cost,
                    hipaa_state=compliance.state,
                    hipaa_score=compliance.overall_score,
                    security_state=security.state,
                    security_risk_level=security.risk_level,
                    security_risk_score=security.security_score,
                    source_context=source_context,
                    last_discovery_sync_at=last_discovery_sync,
                    last_tested_at=azure_status.last_tested_at,
                )
            )

        return items

    async def get_cloud_accounts(self, db: AsyncSession | None = None) -> list[CloudAccountStatusRead]:
        items: list[CloudAccountStatusRead] = []
        azure_status = await self.get_azure_status(db=db)
        items.append(
            CloudAccountStatusRead(
                provider="azure",
                enabled=azure_status.enabled,
                configuration_state=azure_status.configuration_state,
                connection_state=azure_status.connection_state,
                message=azure_status.message,
                configured_identity_hint=azure_status.configured_subscription_id,
                authenticated_identity=azure_status.authenticated_subscription_id,
                authenticated_name=azure_status.authenticated_subscription_name,
                last_tested_at=azure_status.last_tested_at,
            )
        )
        items.append(await self.get_cloud_account_status(provider="aws", db=db))
        items.append(await self.get_cloud_account_status(provider="gcp", db=db))
        return items

    async def get_cloud_account_status(self, provider: str, db: AsyncSession | None = None) -> CloudAccountStatusRead:
        normalized = str(provider or "").strip().lower()
        if normalized == "azure":
            azure_status = await self.get_azure_status(db=db)
            return CloudAccountStatusRead(
                provider="azure",
                enabled=azure_status.enabled,
                configuration_state=azure_status.configuration_state,
                connection_state=azure_status.connection_state,
                message=azure_status.message,
                configured_identity_hint=azure_status.configured_subscription_id,
                authenticated_identity=azure_status.authenticated_subscription_id,
                authenticated_name=azure_status.authenticated_subscription_name,
                last_tested_at=azure_status.last_tested_at,
            )

        if normalized not in {"aws", "gcp"}:
            return CloudAccountStatusRead(
                provider=normalized,
                enabled=False,
                configuration_state="not_configured",
                connection_state="not_configured",
                message="Cloud provider is not supported.",
            )

        credentials = await self._get_cloud_credentials(normalized, db=db)
        configured = self._cloud_credentials_configured(normalized, credentials)
        snapshot = self._cloud_account_connection.get(normalized, _CloudAccountSnapshot())
        message = snapshot.message
        state = snapshot.state
        if not configured:
            state = "not_configured"
            message = self._cloud_not_configured_message(normalized)

        return CloudAccountStatusRead(
            provider=normalized,
            enabled=configured,
            configuration_state="configured" if configured else "not_configured",
            connection_state=state,
            message=message,
            configured_identity_hint=self._configured_cloud_identity_hint(normalized, credentials),
            authenticated_identity=snapshot.authenticated_identity,
            authenticated_name=snapshot.authenticated_name,
            last_tested_at=snapshot.last_tested_at,
        )

    async def save_cloud_account_credentials(
        self,
        provider: str,
        payload: CloudAccountCredentialsWrite,
        db: AsyncSession | None = None,
    ) -> CloudAccountStatusRead:
        normalized = str(provider or "").strip().lower()
        if normalized == "azure":
            raise ValueError("Use dedicated Azure credentials endpoint")
        if normalized not in {"aws", "gcp"}:
            raise ValueError("Unsupported cloud provider")

        submitted = self._sanitize_cloud_credentials(normalized, payload.model_dump())
        existing = await self._get_cloud_credentials(normalized, db=db)
        merged = self._merge_cloud_credentials(normalized, existing, submitted)
        configured = self._cloud_credentials_configured(normalized, merged)

        if not configured:
            self._set_cloud_runtime_credentials(normalized, merged)
            self._cloud_account_connection[normalized] = _CloudAccountSnapshot(
                state="not_configured",
                message=self._cloud_not_configured_message(normalized),
            )
            if db is not None:
                await self._save_cloud_credentials_to_db(normalized, merged, db=db)
            return await self.get_cloud_account_status(normalized, db=db)

        self._set_cloud_runtime_credentials(normalized, merged)
        self._cloud_account_connection[normalized] = _CloudAccountSnapshot(
            state="unavailable",
            message=f"{normalized.upper()} credentials saved. Run Test Connection to validate authentication.",
        )

        if db is not None:
            await self._save_cloud_credentials_to_db(normalized, merged, db=db)

        return await self.get_cloud_account_status(normalized, db=db)

    async def clear_cloud_account_credentials(self, provider: str, db: AsyncSession | None = None) -> CloudAccountStatusRead:
        normalized = str(provider or "").strip().lower()
        if normalized == "azure":
            raise ValueError("Use dedicated Azure credentials endpoint")
        if normalized not in {"aws", "gcp"}:
            raise ValueError("Unsupported cloud provider")

        self._set_cloud_runtime_credentials(normalized, {})
        self._cloud_account_connection[normalized] = _CloudAccountSnapshot(
            state="not_configured",
            message=self._cloud_not_configured_message(normalized),
        )

        if db is not None:
            await self._save_cloud_credentials_to_db(normalized, {}, db=db)

        return await self.get_cloud_account_status(normalized, db=db)

    async def test_cloud_account_connection(self, provider: str, db: AsyncSession | None = None) -> CloudAccountStatusRead:
        normalized = str(provider or "").strip().lower()
        if normalized == "azure":
            azure = await self.test_azure_connection(db=db)
            return CloudAccountStatusRead(
                provider="azure",
                enabled=azure.enabled,
                configuration_state=azure.configuration_state,
                connection_state=azure.connection_state,
                message=azure.message,
                configured_identity_hint=azure.configured_subscription_id,
                authenticated_identity=azure.authenticated_subscription_id,
                authenticated_name=azure.authenticated_subscription_name,
                last_tested_at=azure.last_tested_at,
            )
        if normalized not in {"aws", "gcp"}:
            raise ValueError("Unsupported cloud provider")

        credentials = await self._get_cloud_credentials(normalized, db=db)
        if not self._cloud_credentials_configured(normalized, credentials):
            snapshot = _CloudAccountSnapshot(
                state="not_configured",
                message=self._cloud_not_configured_message(normalized),
                last_tested_at=self._now_utc_iso(),
            )
            self._cloud_account_connection[normalized] = snapshot
            return await self.get_cloud_account_status(normalized, db=db)

        self._set_cloud_runtime_credentials(normalized, credentials)

        if normalized == "aws":
            snapshot = await self._test_aws_connection(credentials)
        else:
            snapshot = await self._test_gcp_connection(credentials)

        self._cloud_account_connection[normalized] = snapshot
        return await self.get_cloud_account_status(normalized, db=db)

    async def _provider_status(self, provider: str, db: AsyncSession | None = None) -> ProviderStatusRead:
        configured = bool(await self._get_provider_key(provider, db=db))
        config_state = "configured" if configured else "not_configured"
        previous = self._provider_connection.get(provider, _ConnectionSnapshot())
        state = previous.state
        message = previous.message

        if not configured:
            state = "not_configured"
            if not message:
                message = "Provider key is not configured."

        return ProviderStatusRead(
            provider=provider,
            enabled=configured,
            configuration_state=config_state,
            connection_state=state,
            message=message,
        )

    async def test_provider_connection(self, provider: str, db: AsyncSession | None = None) -> ProviderConnectionTestRead:
        key = await self._get_provider_key(provider, db=db)
        if not key:
            result = ProviderConnectionTestRead(
                provider=provider,
                state="not_configured",
                message="Provider key is not configured.",
            )
            self._provider_connection[provider] = _ConnectionSnapshot(state=result.state, message=result.message)
            return result

        if provider == "openai":
            result = await self._test_openai(key)
        else:
            result = await self._test_gemini(key)

        self._provider_connection[provider] = _ConnectionSnapshot(state=result.state, message=result.message)
        return result

    async def _test_openai(self, api_key: str) -> ProviderConnectionTestRead:
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                response = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            return self._to_provider_state("openai", response.status_code)
        except Exception:
            return ProviderConnectionTestRead(
                provider="openai",
                state="provider_error",
                message="Provider is unavailable or not reachable.",
            )

    async def _test_gemini(self, api_key: str) -> ProviderConnectionTestRead:
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                response = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    params={"key": api_key},
                )
            return self._to_provider_state("gemini", response.status_code)
        except Exception:
            return ProviderConnectionTestRead(
                provider="gemini",
                state="provider_error",
                message="Provider is unavailable or not reachable.",
            )

    def _to_provider_state(self, provider: str, status_code: int) -> ProviderConnectionTestRead:
        if 200 <= status_code < 300:
            return ProviderConnectionTestRead(provider=provider, state="configured", message="Provider connection test succeeded.")
        if status_code == 401:
            return ProviderConnectionTestRead(provider=provider, state="authentication_failure", message="Provider authentication failed.")
        if status_code == 403:
            return ProviderConnectionTestRead(provider=provider, state="permission_failure", message="Provider permission denied.")
        return ProviderConnectionTestRead(provider=provider, state="provider_error", message="Provider returned an unavailable or unexpected response.")

    async def save_azure_credentials(self, payload: AzureCredentialsWrite, db: AsyncSession | None = None) -> AzureIntegrationStatusRead:
        submitted = {
            "tenant_id": (payload.tenant_id or "").strip(),
            "client_id": (payload.client_id or "").strip(),
            "client_secret": (payload.client_secret or "").strip(),
            "subscription_id": (payload.subscription_id or "").strip(),
        }

        existing = await self._get_azure_credentials(db=db)
        credentials = {
            "tenant_id": submitted["tenant_id"] or existing.get("tenant_id", ""),
            "client_id": submitted["client_id"] or existing.get("client_id", ""),
            "client_secret": submitted["client_secret"] or existing.get("client_secret", ""),
            "subscription_id": submitted["subscription_id"] or existing.get("subscription_id", ""),
        }

        configured = all(credentials.values())
        if not configured:
            return AzureIntegrationStatusRead(
                enabled=False,
                configuration_state="not_configured",
                connection_state="not_configured",
                message="Azure credentials are incomplete. Provide tenant_id, client_id, subscription_id, and client_secret at least once.",
            )

        type(self)._azure_runtime_credentials = credentials
        self._sync_azure_env(credentials)
        self._set_azure_connection_snapshot(_ConnectionSnapshot(
            state="unavailable",
            message="Azure credentials saved. Run Test Azure Connection to validate authentication.",
        ))

        if db is not None:
            await self._save_azure_credentials_to_db(credentials, db=db)

        return await self.get_azure_status(db=db)

    async def clear_azure_credentials(self, db: AsyncSession | None = None) -> AzureIntegrationStatusRead:
        type(self)._azure_runtime_credentials = {}
        self._sync_azure_env({})
        self._set_azure_connection_snapshot(
            _ConnectionSnapshot(state="not_configured", message="Azure credentials are not configured.")
        )

        if db is not None:
            await self._save_azure_credentials_to_db({}, db=db)

        return await self.get_azure_status(db=db)

    async def get_azure_status(self, db: AsyncSession | None = None) -> AzureIntegrationStatusRead:
        credentials = await self._get_azure_credentials(db=db)
        tenant_id = credentials.get("tenant_id", "")
        client_id = credentials.get("client_id", "")
        client_secret = credentials.get("client_secret", "")
        subscription_id = credentials.get("subscription_id", "")
        configured = bool(tenant_id and client_id and client_secret and subscription_id)
        config_state = "configured" if configured else "not_configured"
        discovered_resource_groups, discovered_resources, last_discovery_sync = await self._azure_discovery_metrics(
            db=db,
            external_subscription_id=subscription_id,
        )

        if not configured or ClientSecretCredential is None:
            message = "Azure credentials are not configured."
            if ClientSecretCredential is None:
                message = "azure-identity is not installed; Azure integration is unavailable."
            return AzureIntegrationStatusRead(
                enabled=False,
                configuration_state="not_configured",
                connection_state="not_configured",
                message=message,
                configured_tenant_id=tenant_id or None,
                configured_subscription_id=subscription_id or None,
                configured_client_id_hint=self._mask_client_id(client_id),
                discovered_resource_group_count=discovered_resource_groups,
                discovered_resource_count=discovered_resources,
                last_discovery_sync_at=last_discovery_sync,
            )

        previous = self._azure_connection
        return AzureIntegrationStatusRead(
            enabled=True,
            configuration_state=config_state,
            connection_state=previous.state,
            message=previous.message,
            configured_tenant_id=tenant_id or None,
            configured_subscription_id=subscription_id or None,
            configured_client_id_hint=self._mask_client_id(client_id),
            authenticated_tenant_id=previous.authenticated_tenant_id,
            authenticated_subscription_id=previous.authenticated_subscription_id,
            authenticated_subscription_name=previous.authenticated_subscription_name,
            authenticated_subscription_state=previous.authenticated_subscription_state,
            discovered_resource_group_count=discovered_resource_groups,
            discovered_resource_count=discovered_resources,
            last_discovery_sync_at=last_discovery_sync,
            last_tested_at=previous.last_tested_at,
        )

    def _latest_discovery_sync(self, *, groups: list[AzureResourceGroup], resources: list[ArchitectureResource]) -> str | None:
        stamps: list[str] = []
        for group in groups:
            props = group.properties if isinstance(group.properties, dict) else {}
            stamp = str(props.get("discovery_last_seen_at") or "").strip()
            if stamp:
                stamps.append(stamp)
        for resource in resources:
            props = resource.properties if isinstance(resource.properties, dict) else {}
            stamp = str(props.get("discovery_last_seen_at") or "").strip()
            if stamp:
                stamps.append(stamp)
        if not stamps:
            return None
        return max(stamps)

    async def _azure_discovery_metrics(
        self,
        *,
        db: AsyncSession | None,
        external_subscription_id: str,
    ) -> tuple[int, int, str | None]:
        if db is None:
            return 0, 0, None

        normalized_external_id = str(external_subscription_id or "").strip().lower()
        if not normalized_external_id:
            return 0, 0, None

        subs_result = await db.execute(
            select(AzureSubscription).where(
                AzureSubscription.subscription_id.is_not(None),
                AzureSubscription.subscription_id.ilike(normalized_external_id),
            )
        )
        subscriptions = list(subs_result.scalars().all())
        if not subscriptions:
            return 0, 0, None

        sub_ids = [item.id for item in subscriptions]
        sub_external_ids = {
            str(item.subscription_id or "").strip().lower()
            for item in subscriptions
            if str(item.subscription_id or "").strip()
        }

        groups_result = await db.execute(
            select(AzureResourceGroup).where(AzureResourceGroup.subscription_id.in_(sub_ids))
        )
        groups = list(groups_result.scalars().all())
        group_id_set = {group.id for group in groups}

        resources_result = await db.execute(
            select(ArchitectureResource).where(
                and_(
                    ArchitectureResource.architecture_id.in_([item.architecture_id for item in subscriptions]),
                    ArchitectureResource.resource_group_id.is_not(None),
                )
            )
        )
        candidate_resources = list(resources_result.scalars().all())

        resources: list[ArchitectureResource] = []
        for resource in candidate_resources:
            if resource.resource_group_id in group_id_set:
                resources.append(resource)
                continue

            props = resource.properties if isinstance(resource.properties, dict) else {}
            resource_external_id = str(props.get("azure_subscription_id") or "").strip().lower()
            if resource_external_id and resource_external_id in sub_external_ids:
                resources.append(resource)

        return len(groups), len(resources), self._latest_discovery_sync(groups=groups, resources=resources)

    async def test_azure_connection(self, db: AsyncSession | None = None) -> AzureIntegrationStatusRead:
        credentials = await self._get_azure_credentials(db=db)
        tenant_id = credentials.get("tenant_id", "")
        client_id = credentials.get("client_id", "")
        client_secret = credentials.get("client_secret", "")
        subscription_id = credentials.get("subscription_id", "")

        if ClientSecretCredential is None or not tenant_id or not client_id or not client_secret or not subscription_id:
            message = "Azure credentials are not configured."
            if ClientSecretCredential is None:
                message = "azure-identity is not installed; Azure integration is unavailable."
            snapshot = _ConnectionSnapshot(
                state="not_configured",
                message=message,
                last_tested_at=self._now_utc_iso(),
            )
            self._set_azure_connection_snapshot(snapshot)
            return AzureIntegrationStatusRead(
                enabled=False,
                configuration_state="not_configured",
                connection_state="not_configured",
                message=message,
                configured_tenant_id=tenant_id or None,
                configured_subscription_id=subscription_id or None,
                configured_client_id_hint=self._mask_client_id(client_id),
                last_tested_at=snapshot.last_tested_at,
            )

        type(self)._azure_runtime_credentials = credentials
        self._sync_azure_env(credentials)

        try:
            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
            )
            token = credential.get_token("https://management.azure.com/.default")
        except Exception as exc:
            message = "Azure authentication failed."
            detail = str(exc).strip()
            if detail:
                message = f"{message} {detail}"
            snapshot = _ConnectionSnapshot(
                state="authentication_failure",
                message=message,
                last_tested_at=self._now_utc_iso(),
            )
            self._set_azure_connection_snapshot(snapshot)
            return AzureIntegrationStatusRead(
                enabled=True,
                configuration_state="configured",
                connection_state="authentication_failure",
                message=message,
                configured_tenant_id=tenant_id or None,
                configured_subscription_id=subscription_id or None,
                configured_client_id_hint=self._mask_client_id(client_id),
                last_tested_at=snapshot.last_tested_at,
            )

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"https://management.azure.com/subscriptions/{subscription_id}",
                    params={"api-version": "2020-01-01"},
                    headers={"Authorization": f"Bearer {token.token}"},
                )
        except Exception as exc:
            message = "Azure provider is unavailable or not reachable."
            detail = str(exc).strip()
            if detail:
                message = f"{message} {detail}"
            snapshot = _ConnectionSnapshot(
                state="provider_error",
                message=message,
                last_tested_at=self._now_utc_iso(),
            )
            self._set_azure_connection_snapshot(snapshot)
            return AzureIntegrationStatusRead(
                enabled=True,
                configuration_state="configured",
                connection_state="provider_error",
                message=message,
                configured_tenant_id=tenant_id or None,
                configured_subscription_id=subscription_id or None,
                configured_client_id_hint=self._mask_client_id(client_id),
                last_tested_at=snapshot.last_tested_at,
            )

        if response.status_code == 401:
            state = "authentication_failure"
            message = "Azure authentication failed."
            detail = self._azure_error_message_from_response(response)
            if detail:
                message = f"{message} {detail}"
            snapshot = _ConnectionSnapshot(state=state, message=message, last_tested_at=self._now_utc_iso())
        elif response.status_code == 403:
            state = "permission_failure"
            message = "Azure permission denied for subscription access."
            detail = self._azure_error_message_from_response(response)
            if detail:
                message = f"{message} {detail}"
            snapshot = _ConnectionSnapshot(state=state, message=message, last_tested_at=self._now_utc_iso())
        elif 200 <= response.status_code < 300:
            state = "configured"
            message = "Azure connection test succeeded."
            try:
                payload = response.json()
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            snapshot = _ConnectionSnapshot(
                state=state,
                message=message,
                authenticated_tenant_id=str(payload.get("tenantId") or payload.get("homeTenantId") or tenant_id or "") or None,
                authenticated_subscription_id=str(payload.get("subscriptionId") or subscription_id or "") or None,
                authenticated_subscription_name=str(payload.get("displayName") or "") or None,
                authenticated_subscription_state=str(payload.get("state") or "") or None,
                last_tested_at=self._now_utc_iso(),
            )
        else:
            state = "provider_error"
            message = "Azure provider returned an unavailable or unexpected response."
            detail = self._azure_error_message_from_response(response)
            if detail:
                message = f"{message} {detail}"
            snapshot = _ConnectionSnapshot(state=state, message=message, last_tested_at=self._now_utc_iso())

        self._set_azure_connection_snapshot(snapshot)
        return AzureIntegrationStatusRead(
            enabled=True,
            configuration_state="configured",
            connection_state=state,
            message=message,
            configured_tenant_id=tenant_id or None,
            configured_subscription_id=subscription_id or None,
            configured_client_id_hint=self._mask_client_id(client_id),
            authenticated_tenant_id=snapshot.authenticated_tenant_id,
            authenticated_subscription_id=snapshot.authenticated_subscription_id,
            authenticated_subscription_name=snapshot.authenticated_subscription_name,
            authenticated_subscription_state=snapshot.authenticated_subscription_state,
            last_tested_at=snapshot.last_tested_at,
        )

    @classmethod
    def get_cached_azure_credentials(cls) -> dict[str, str]:
        return dict(cls._azure_runtime_credentials)

    async def get_azure_credentials_for_backend(self, db: AsyncSession | None = None) -> dict[str, str]:
        """Resolve Settings credentials for backend integrations without returning them via an API."""
        credentials = await self._get_azure_credentials(db=db)
        self._sync_azure_env(credentials)
        type(self)._azure_runtime_credentials = credentials
        return credentials

    async def _get_cloud_credentials(self, provider: str, db: AsyncSession | None = None) -> dict[str, str]:
        normalized = str(provider or "").strip().lower()
        if normalized == "aws":
            runtime = self._sanitize_aws_credentials(self._aws_runtime_credentials)
            if runtime and all(runtime.values()):
                return runtime
        elif normalized == "gcp":
            runtime = self._sanitize_gcp_credentials(self._gcp_runtime_credentials)
            if runtime and runtime.get("service_account_json"):
                return runtime
        else:
            return {}

        db_creds: dict[str, str] = {}
        if db is not None:
            provider_key = _CLOUD_PROVIDER_KEYS.get(normalized)
            row = await db.scalar(select(ProviderConfiguration).where(ProviderConfiguration.provider == provider_key))
            db_creds = self._credentials_from_db_value((row.api_key or "") if row is not None else "")
            if db_creds:
                self._set_cloud_runtime_credentials(normalized, db_creds)
                return self._sanitize_cloud_credentials(normalized, db_creds)

        env_creds = self._cloud_credentials_from_env(normalized)
        if env_creds:
            self._set_cloud_runtime_credentials(normalized, env_creds)
        return env_creds

    async def _save_cloud_credentials_to_db(self, provider: str, credentials: dict[str, str], db: AsyncSession) -> None:
        normalized = str(provider or "").strip().lower()
        provider_key = _CLOUD_PROVIDER_KEYS.get(normalized)
        if not provider_key:
            return
        row = await db.scalar(select(ProviderConfiguration).where(ProviderConfiguration.provider == provider_key))
        value = json.dumps(credentials) if credentials else None
        if row is None and value is not None:
            db.add(ProviderConfiguration(provider=provider_key, api_key=value))
            await db.commit()
            return
        if row is not None:
            row.api_key = value
            await db.commit()

    @staticmethod
    def _sanitize_aws_credentials(source: dict[str, str] | None) -> dict[str, str]:
        if not source:
            return {}
        return {
            "access_key_id": str(source.get("access_key_id") or "").strip(),
            "secret_access_key": str(source.get("secret_access_key") or "").strip(),
            "region": str(source.get("region") or "").strip(),
        }

    @staticmethod
    def _sanitize_gcp_credentials(source: dict[str, str] | None) -> dict[str, str]:
        if not source:
            return {}
        return {
            "service_account_json": str(source.get("service_account_json") or "").strip(),
        }

    def _sanitize_cloud_credentials(self, provider: str, source: dict[str, str] | None) -> dict[str, str]:
        normalized = str(provider or "").strip().lower()
        if normalized == "aws":
            return self._sanitize_aws_credentials(source)
        if normalized == "gcp":
            return self._sanitize_gcp_credentials(source)
        return {}

    def _set_cloud_runtime_credentials(self, provider: str, credentials: dict[str, str]) -> None:
        normalized = str(provider or "").strip().lower()
        if normalized == "aws":
            sanitized = self._sanitize_aws_credentials(credentials)
            type(self)._aws_runtime_credentials = sanitized
            self._sync_aws_env(sanitized)
        elif normalized == "gcp":
            sanitized = self._sanitize_gcp_credentials(credentials)
            type(self)._gcp_runtime_credentials = sanitized
            self._sync_gcp_env(sanitized)

    def _merge_cloud_credentials(self, provider: str, existing: dict[str, str], submitted: dict[str, str]) -> dict[str, str]:
        normalized = str(provider or "").strip().lower()
        if normalized == "aws":
            return {
                "access_key_id": submitted.get("access_key_id") or existing.get("access_key_id", ""),
                "secret_access_key": submitted.get("secret_access_key") or existing.get("secret_access_key", ""),
                "region": submitted.get("region") or existing.get("region", ""),
            }
        if normalized == "gcp":
            return {
                "service_account_json": submitted.get("service_account_json") or existing.get("service_account_json", ""),
            }
        return {}

    def _cloud_credentials_configured(self, provider: str, credentials: dict[str, str]) -> bool:
        normalized = str(provider or "").strip().lower()
        if normalized == "aws":
            return bool(credentials.get("access_key_id") and credentials.get("secret_access_key") and credentials.get("region"))
        if normalized == "gcp":
            payload = str(credentials.get("service_account_json") or "").strip()
            if not payload:
                return False
            try:
                parsed = json.loads(payload)
            except Exception:
                return False
            return isinstance(parsed, dict) and bool(parsed.get("project_id")) and bool(parsed.get("client_email"))
        return False

    def _cloud_not_configured_message(self, provider: str) -> str:
        if provider == "aws":
            return "AWS credentials are incomplete. Provide access_key_id, secret_access_key, and region."
        if provider == "gcp":
            return "GCP credentials are incomplete. Provide a valid service account JSON payload."
        return "Cloud credentials are not configured."

    def _configured_cloud_identity_hint(self, provider: str, credentials: dict[str, str]) -> str | None:
        if provider == "aws":
            return self._mask_client_id(str(credentials.get("access_key_id") or ""))
        if provider == "gcp":
            raw = str(credentials.get("service_account_json") or "").strip()
            if not raw:
                return None
            try:
                parsed = json.loads(raw)
            except Exception:
                return None
            project_id = str(parsed.get("project_id") or "").strip()
            if project_id:
                return project_id
            return None
        return None

    def _cloud_credentials_from_env(self, provider: str) -> dict[str, str]:
        if provider == "aws":
            return self._sanitize_aws_credentials(
                {
                    key: (os.getenv(env_name) or "").strip()
                    for key, env_name in _AWS_ENV_KEYS.items()
                }
            )
        if provider == "gcp":
            return self._sanitize_gcp_credentials(
                {
                    key: (os.getenv(env_name) or "").strip()
                    for key, env_name in _GCP_ENV_KEYS.items()
                }
            )
        return {}

    async def _test_aws_connection(self, credentials: dict[str, str]) -> _CloudAccountSnapshot:
        try:
            import boto3
            from botocore.exceptions import ClientError, NoCredentialsError
        except Exception:
            return _CloudAccountSnapshot(
                state="provider_error",
                message="boto3 is not installed; AWS connection test is unavailable.",
                last_tested_at=self._now_utc_iso(),
            )

        try:
            session = boto3.Session(
                aws_access_key_id=credentials.get("access_key_id"),
                aws_secret_access_key=credentials.get("secret_access_key"),
                region_name=credentials.get("region"),
            )
            identity = session.client("sts").get_caller_identity()
            return _CloudAccountSnapshot(
                state="configured",
                message="AWS connection test succeeded.",
                authenticated_identity=str(identity.get("Account") or "") or None,
                authenticated_name=str(identity.get("Arn") or "") or None,
                last_tested_at=self._now_utc_iso(),
            )
        except NoCredentialsError:
            return _CloudAccountSnapshot(
                state="authentication_failure",
                message="AWS authentication failed.",
                last_tested_at=self._now_utc_iso(),
            )
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code") or "").strip()
            if code in {"InvalidClientTokenId", "SignatureDoesNotMatch", "AuthFailure", "UnrecognizedClientException"}:
                state = "authentication_failure"
                message = "AWS authentication failed."
            elif code in {"AccessDenied", "AccessDeniedException"}:
                state = "permission_failure"
                message = "AWS permission denied."
            else:
                state = "provider_error"
                message = "AWS provider returned an unavailable or unexpected response."
            detail = str(exc).strip()
            if detail:
                message = f"{message} {detail}"
            return _CloudAccountSnapshot(state=state, message=message, last_tested_at=self._now_utc_iso())
        except Exception as exc:
            detail = str(exc).strip()
            message = "AWS provider is unavailable or not reachable."
            if detail:
                message = f"{message} {detail}"
            return _CloudAccountSnapshot(state="provider_error", message=message, last_tested_at=self._now_utc_iso())

    async def _test_gcp_connection(self, credentials: dict[str, str]) -> _CloudAccountSnapshot:
        raw = str(credentials.get("service_account_json") or "").strip()
        try:
            service_account_payload = json.loads(raw)
        except Exception:
            return _CloudAccountSnapshot(
                state="authentication_failure",
                message="GCP service account JSON is invalid.",
                last_tested_at=self._now_utc_iso(),
            )

        try:
            from google.oauth2 import service_account
            from google.auth.transport.requests import Request
        except Exception:
            return _CloudAccountSnapshot(
                state="provider_error",
                message="google-auth is not installed; GCP connection test is unavailable.",
                last_tested_at=self._now_utc_iso(),
            )

        try:
            credentials_obj = service_account.Credentials.from_service_account_info(
                service_account_payload,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            credentials_obj.refresh(Request())
        except Exception as exc:
            detail = str(exc).strip()
            message = "GCP authentication failed."
            if detail:
                message = f"{message} {detail}"
            return _CloudAccountSnapshot(state="authentication_failure", message=message, last_tested_at=self._now_utc_iso())

        project_id = str(service_account_payload.get("project_id") or "").strip()
        if project_id and credentials_obj.token:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.get(
                        f"https://cloudresourcemanager.googleapis.com/v1/projects/{project_id}",
                        headers={"Authorization": f"Bearer {credentials_obj.token}"},
                    )
                if response.status_code == 403:
                    return _CloudAccountSnapshot(
                        state="permission_failure",
                        message="GCP permission denied for project access.",
                        authenticated_identity=project_id,
                        authenticated_name=str(service_account_payload.get("client_email") or "") or None,
                        last_tested_at=self._now_utc_iso(),
                    )
                if response.status_code == 401:
                    return _CloudAccountSnapshot(
                        state="authentication_failure",
                        message="GCP authentication failed.",
                        last_tested_at=self._now_utc_iso(),
                    )
                if response.status_code >= 400:
                    return _CloudAccountSnapshot(
                        state="provider_error",
                        message="GCP provider returned an unavailable or unexpected response.",
                        last_tested_at=self._now_utc_iso(),
                    )
            except Exception:
                # Token acquisition is sufficient for test success when project metadata probe is unavailable.
                pass

        return _CloudAccountSnapshot(
            state="configured",
            message="GCP connection test succeeded.",
            authenticated_identity=project_id or None,
            authenticated_name=str(service_account_payload.get("client_email") or "") or None,
            last_tested_at=self._now_utc_iso(),
        )

    async def _get_provider_key(self, provider: str, db: AsyncSession | None = None) -> str:
        runtime_value = (self._runtime_secrets.get(provider) or "").strip()
        if runtime_value:
            return runtime_value

        if db is not None:
            row = await db.scalar(select(ProviderConfiguration).where(ProviderConfiguration.provider == provider))
            persisted_value = (row.api_key or "").strip() if row is not None else ""
            if persisted_value:
                return persisted_value

        env_name = _PROVIDER_ENV_KEYS.get(provider)
        return (os.getenv(env_name) or "").strip() if env_name else ""

    async def _get_azure_credentials(self, db: AsyncSession | None = None) -> dict[str, str]:
        runtime = self._sanitize_azure_credentials(self._azure_runtime_credentials)
        if runtime and all(runtime.values()):
            return runtime

        db_creds: dict[str, str] = {}
        if db is not None:
            row = await db.scalar(select(ProviderConfiguration).where(ProviderConfiguration.provider == _AZURE_PROVIDER_KEY))
            db_creds = self._credentials_from_db_value((row.api_key or "") if row is not None else "")
            if db_creds:
                self._azure_runtime_credentials = db_creds
                self._sync_azure_env(db_creds)
                return db_creds

        env_creds = self._sanitize_azure_credentials(
            {
                key: (os.getenv(env_name) or "").strip()
                for key, env_name in _AZURE_ENV_KEYS.items()
            }
        )
        if env_creds:
            self._azure_runtime_credentials = env_creds
        return env_creds

    async def _save_azure_credentials_to_db(self, credentials: dict[str, str], db: AsyncSession) -> None:
        row = await db.scalar(select(ProviderConfiguration).where(ProviderConfiguration.provider == _AZURE_PROVIDER_KEY))
        value = json.dumps(credentials) if credentials else None
        if row is None and value is not None:
            db.add(ProviderConfiguration(provider=_AZURE_PROVIDER_KEY, api_key=value))
            await db.commit()
            return
        if row is not None:
            row.api_key = value
            await db.commit()

    @staticmethod
    def _sanitize_azure_credentials(source: dict[str, str] | None) -> dict[str, str]:
        if not source:
            return {}
        return {
            "tenant_id": str(source.get("tenant_id") or "").strip(),
            "client_id": str(source.get("client_id") or "").strip(),
            "client_secret": str(source.get("client_secret") or "").strip(),
            "subscription_id": str(source.get("subscription_id") or "").strip(),
        }

    @staticmethod
    def _credentials_from_db_value(value: str) -> dict[str, str]:
        raw = str(value or "").strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except Exception:
            return {}
        if not isinstance(parsed, dict):
            return {}
        return SettingsService._sanitize_azure_credentials(parsed)

    @staticmethod
    def _sync_azure_env(credentials: dict[str, str]) -> None:
        normalized = SettingsService._sanitize_azure_credentials(credentials)
        for key, env_name in _AZURE_ENV_KEYS.items():
            value = normalized.get(key, "")
            if value:
                os.environ[env_name] = value
            elif env_name in os.environ:
                del os.environ[env_name]

    @staticmethod
    def _sync_aws_env(credentials: dict[str, str]) -> None:
        normalized = SettingsService._sanitize_aws_credentials(credentials)
        for key, env_name in _AWS_ENV_KEYS.items():
            value = normalized.get(key, "")
            if value:
                os.environ[env_name] = value
            elif env_name in os.environ:
                del os.environ[env_name]

    @staticmethod
    def _sync_gcp_env(credentials: dict[str, str]) -> None:
        normalized = SettingsService._sanitize_gcp_credentials(credentials)
        for key, env_name in _GCP_ENV_KEYS.items():
            value = normalized.get(key, "")
            if value:
                os.environ[env_name] = value
            elif env_name in os.environ:
                del os.environ[env_name]
