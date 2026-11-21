from __future__ import annotations

from pydantic import BaseModel, Field


class GovernanceComplianceRequest(BaseModel):
    frameworks: list[str] = Field(default_factory=list)


class GovernanceComplianceControlRead(BaseModel):
    control_id: str
    title: str
    severity: str
    description: str
    remediation: str
    resource_types: list[str] = Field(default_factory=list)


class GovernanceComplianceFindingRead(BaseModel):
    finding_id: str
    framework: str
    control_id: str
    title: str
    severity: str
    status: str
    message: str
    remediation: str
    resource_id: str | None = None
    resource_name: str | None = None
    resource_type: str | None = None


class GovernanceComplianceFrameworkSummaryRead(BaseModel):
    framework: str
    status: str
    score: int
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0


class GovernanceComplianceSummaryRead(BaseModel):
    architecture_id: str
    source: str = "legacy_compliance_engine"
    state: str
    frameworks: list[str] = Field(default_factory=list)
    compliant: bool | None = None
    overall_score: int | None = None
    evaluated_resources: int = 0
    total_findings: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    violations: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    controls: list[GovernanceComplianceControlRead] = Field(default_factory=list)
    findings: list[GovernanceComplianceFindingRead] = Field(default_factory=list)
    framework_results: list[GovernanceComplianceFrameworkSummaryRead] = Field(default_factory=list)
    azure_connection_state: str | None = None
    azure_connection_message: str | None = None
    live_connected: bool = False
    message: str | None = None


class GovernanceSecurityRequest(BaseModel):
    pass


class GovernanceSecurityFindingRead(BaseModel):
    id: str
    resource_id: str | None = None
    resource_name: str
    resource_type: str
    severity: str
    title: str
    description: str
    recommendation: str
    category: str | None = None


class GovernanceSecuritySecretRead(BaseModel):
    id: str
    resource_id: str | None = None
    resource_name: str
    resource_type: str
    type: str
    location: str
    description: str
    severity: str


class GovernanceSecuritySummaryRead(BaseModel):
    architecture_id: str
    source: str = "legacy_security_engine"
    state: str
    risk_level: str
    security_score: float
    evaluated_resources: int = 0
    total_findings: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    secrets_count: int = 0
    findings: list[GovernanceSecurityFindingRead] = Field(default_factory=list)
    secrets: list[GovernanceSecuritySecretRead] = Field(default_factory=list)
    message: str | None = None
