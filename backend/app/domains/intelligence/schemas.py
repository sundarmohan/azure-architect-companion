from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


ProviderName = Literal["openai", "gemini", "deterministic_fallback"]
ProviderState = Literal[
    "configured",
    "not_configured",
    "authentication_failure",
    "permission_failure",
    "provider_error",
    "unavailable",
]


class IntelligenceAnalysisRequest(BaseModel):
    provider: ProviderName | None = None


class IntelligenceFindingRead(BaseModel):
    id: str
    category: str
    severity: str
    title: str
    description: str
    rationale: str
    affected_resources: list[str] = Field(default_factory=list)
    recommendation: str
    source: str
    confidence: float


class IntelligenceRecommendationRead(BaseModel):
    id: str
    title: str
    category: str
    severity: str
    rationale: str
    recommendation: str
    affected_resources: list[str] = Field(default_factory=list)
    source: str
    confidence: float


class IntelligenceRiskRead(BaseModel):
    id: str
    title: str
    priority: str
    explanation: str
    impact: str
    source: str
    confidence: float


class IntelligenceObservedFactRead(BaseModel):
    id: str
    fact: str
    source: str
    evidence: str | None = None
    confidence: float


class IntelligenceRcaRead(BaseModel):
    id: str
    affected_resource: str
    observed_symptom: str
    related_dependency: str | None = None
    probable_cause: str
    supporting_evidence: list[str] = Field(default_factory=list)
    impact: str
    recommended_action: str
    confidence: float


class IntelligenceIncidentCorrelationRead(BaseModel):
    incident_id: str
    title: str
    severity: str
    status: str
    resource_name: str | None = None
    monitoring_state: str | None = None
    correlation_reason: str
    recommended_action: str


class IntelligenceAnalysisRead(BaseModel):
    architecture_id: str
    status: str = "success"
    source: str = "monitorai_deterministic_intelligence"
    provider: ProviderName = "deterministic_fallback"
    requested_provider: ProviderName | None = None
    error_state: ProviderState | None = None
    state: str
    overall_assessment: str
    finding_count: int = 0
    severity_summary: dict[str, int] = Field(default_factory=dict)
    observed_facts: list[IntelligenceObservedFactRead] = Field(default_factory=list)
    findings: list[IntelligenceFindingRead] = Field(default_factory=list)
    recommendations: list[IntelligenceRecommendationRead] = Field(default_factory=list)
    risks: list[IntelligenceRiskRead] = Field(default_factory=list)
    rca: list[IntelligenceRcaRead] = Field(default_factory=list)
    incident_correlations: list[IntelligenceIncidentCorrelationRead] = Field(default_factory=list)
    analysis_confidence: float = 0.0
    limitations: list[str] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    message: str | None = None
