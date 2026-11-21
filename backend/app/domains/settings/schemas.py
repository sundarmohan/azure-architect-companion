from typing import Literal

from pydantic import BaseModel, Field

ConfigurationState = Literal["configured", "not_configured"]
ConnectionState = Literal[
    "configured",
    "not_configured",
    "authentication_failure",
    "permission_failure",
    "provider_error",
    "unavailable",
]


class ProviderConfigWrite(BaseModel):
    api_key: str = Field(min_length=1, max_length=4096)


class AzureCredentialsWrite(BaseModel):
    tenant_id: str = Field(min_length=0, max_length=200)
    client_id: str = Field(min_length=0, max_length=200)
    client_secret: str = Field(min_length=0, max_length=4096)
    subscription_id: str = Field(min_length=0, max_length=200)


class ProviderStatusRead(BaseModel):
    provider: str
    enabled: bool
    configuration_state: ConfigurationState
    connection_state: ConnectionState = "unavailable"
    message: str | None = None


class ProviderConnectionTestRead(BaseModel):
    provider: str
    state: ConnectionState
    message: str | None = None


class AzureIntegrationStatusRead(BaseModel):
    enabled: bool
    configuration_state: ConfigurationState
    connection_state: ConnectionState
    message: str | None = None
    configured_tenant_id: str | None = None
    configured_subscription_id: str | None = None
    configured_client_id_hint: str | None = None
    authenticated_tenant_id: str | None = None
    authenticated_subscription_id: str | None = None
    authenticated_subscription_name: str | None = None
    authenticated_subscription_state: str | None = None
    discovered_resource_group_count: int = 0
    discovered_resource_count: int = 0
    last_discovery_sync_at: str | None = None
    last_tested_at: str | None = None


class AzureSubscriptionInventoryRead(BaseModel):
    architecture_id: str
    architecture_name: str
    architecture_status: str
    subscription_db_id: str
    subscription_name: str
    subscription_id: str | None = None
    tenant_id: str | None = None
    connection_state: ConnectionState
    authentication_state: ConnectionState
    resource_group_count: int = 0
    resource_count: int = 0
    monitored_resource_count: int = 0
    live_resource_count: int = 0
    monitoring_state: str = "no_data"
    active_alert_count: int = 0
    active_incident_count: int = 0
    unused_resource_count: int = 0
    estimated_monthly_waste: float = 0.0
    estimated_monthly_cost: float = 0.0
    hipaa_state: str = "not_evaluated"
    hipaa_score: int | None = None
    security_state: str = "not_evaluated"
    security_risk_level: str | None = None
    security_risk_score: float | None = None
    source_context: str = "designed"
    last_discovery_sync_at: str | None = None
    last_tested_at: str | None = None


class CloudAccountCredentialsWrite(BaseModel):
    access_key_id: str = Field(min_length=0, max_length=200)
    secret_access_key: str = Field(min_length=0, max_length=4096)
    region: str = Field(min_length=0, max_length=100)
    service_account_json: str = Field(min_length=0, max_length=20000)


class CloudAccountStatusRead(BaseModel):
    provider: str
    enabled: bool
    configuration_state: ConfigurationState
    connection_state: ConnectionState
    message: str | None = None
    configured_identity_hint: str | None = None
    authenticated_identity: str | None = None
    authenticated_name: str | None = None
    last_tested_at: str | None = None


class SettingsOverviewRead(BaseModel):
    ai_providers: list[ProviderStatusRead]
    azure_integration: AzureIntegrationStatusRead
    cloud_accounts: list[CloudAccountStatusRead] = Field(default_factory=list)
    provider_contract: list[str] = Field(default_factory=lambda: ["openai", "gemini", "deterministic_fallback"])