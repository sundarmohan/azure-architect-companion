from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from typing import Any, Protocol

import httpx

from app.domains.intelligence.legacy_ai_recommendation_service import recommend_architecture
from app.domains.intelligence.schemas import (
    IntelligenceAnalysisRead,
    IntelligenceFindingRead,
    IntelligenceIncidentCorrelationRead,
    IntelligenceObservedFactRead,
    IntelligenceRcaRead,
    IntelligenceRecommendationRead,
    IntelligenceRiskRead,
)


@dataclass
class IntelligenceContext:
    architecture_id: str
    architecture_name: str
    architecture_provider: str
    resources: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    resource_groups: list[dict[str, Any]]
    subscriptions: list[dict[str, Any]]
    monitoring_summary: dict[str, Any] | None
    cost_estimate: dict[str, Any] | None
    actual_cost: dict[str, Any] | None
    compliance_summary: dict[str, Any] | None
    security_summary: dict[str, Any] | None
    incident_summary: dict[str, Any] | None


@dataclass
class ProviderExecutionResult:
    provider: str
    source: str
    state: str
    overall_assessment: str | None
    findings: list[IntelligenceFindingRead]
    recommendations: list[IntelligenceRecommendationRead]
    risks: list[IntelligenceRiskRead]
    observed_facts: list[IntelligenceObservedFactRead]
    rca: list[IntelligenceRcaRead]
    incident_correlations: list[IntelligenceIncidentCorrelationRead]
    analysis_confidence: float
    limitations: list[str]
    message: str | None = None


class AnalysisProvider(Protocol):
    async def analyze(self, context: IntelligenceContext) -> ProviderExecutionResult:
        ...


def compact_intelligence_context(context: IntelligenceContext) -> dict[str, Any]:
    monitoring = context.monitoring_summary or {}
    cost_estimate = context.cost_estimate or {}
    security = context.security_summary or {}
    compliance = context.compliance_summary or {}
    incidents = context.incident_summary or {}

    resource_rows = [
        {
            "name": item.get("name"),
            "type": item.get("resource_type"),
            "location": item.get("location"),
            "group": item.get("resource_group_id"),
        }
        for item in context.resources[:120]
    ]
    relationship_rows = [
        {
            "source": item.get("source_resource_id"),
            "target": item.get("target_resource_id"),
            "type": item.get("relationship_type"),
        }
        for item in context.relationships[:220]
    ]

    return {
        "architecture": {
            "id": context.architecture_id,
            "name": context.architecture_name,
            "provider": context.architecture_provider,
            "subscriptions": len(context.subscriptions),
            "resource_groups": len(context.resource_groups),
            "resources": len(context.resources),
            "relationships": len(context.relationships),
        },
        "resources": resource_rows,
        "relationships": relationship_rows,
        "monitoring": {
            "state": monitoring.get("state"),
            "total_resources": monitoring.get("total_resources"),
            "live_resources": monitoring.get("live_resources"),
            "critical_count": monitoring.get("critical_count"),
            "error_count": monitoring.get("error_count"),
            "failure_signals": [
                {
                    "resource_name": item.get("resource_name"),
                    "resource_type": item.get("resource_type"),
                    "state": item.get("state"),
                    "health_status": item.get("health_status"),
                    "message": item.get("message"),
                }
                for item in (monitoring.get("resources") or [])
                if isinstance(item, dict) and str(item.get("state") or "") in {"not_configured", "authentication_failure", "permission_failure", "azure_api_failure", "no_data", "unsupported"}
            ][:20],
        },
        "incidents": {
            "count": incidents.get("incident_count"),
            "critical_count": incidents.get("critical_count"),
            "high_count": incidents.get("high_count"),
            "items": [
                {
                    "incident_id": item.get("incident_id"),
                    "title": item.get("title"),
                    "severity": item.get("severity"),
                    "status": item.get("status"),
                    "resource_name": item.get("resource_name"),
                    "monitoring_state": item.get("monitoring_state"),
                    "message": item.get("message"),
                }
                for item in (incidents.get("incidents") or [])
                if isinstance(item, dict)
            ][:25],
        },
        "cost": {
            "estimate_source": cost_estimate.get("pricing_source"),
            "estimate_monthly_total": cost_estimate.get("total_monthly_cost"),
            "actual_source": (context.actual_cost or {}).get("pricing_source"),
            "actual_available": (context.actual_cost or {}).get("available"),
            "estimate_top_items": [
                {
                    "name": item.get("name"),
                    "resource_type": item.get("resource_type"),
                    "monthly_cost": item.get("monthly_cost"),
                    "pricing_source": item.get("pricing_source"),
                }
                for item in (cost_estimate.get("items") or [])
                if isinstance(item, dict)
            ][:10],
        },
        "governance": {
            "frameworks": compliance.get("frameworks") or [],
            "compliant": compliance.get("compliant"),
            "violations": len(compliance.get("violations") or []),
            "violation_examples": [str(v) for v in (compliance.get("violations") or [])[:10]],
        },
        "security": {
            "risk_level": security.get("risk_level"),
            "critical_count": security.get("critical_count"),
            "high_count": security.get("high_count"),
            "secrets_count": security.get("secrets_count"),
            "finding_examples": [
                {
                    "title": item.get("title"),
                    "severity": item.get("severity"),
                    "resource_name": item.get("resource_name"),
                }
                for item in (security.get("findings") or [])
                if isinstance(item, dict)
            ][:10],
        },
    }


def _build_observed_facts(context: IntelligenceContext) -> list[IntelligenceObservedFactRead]:
    monitoring = context.monitoring_summary or {}
    incidents = context.incident_summary or {}
    security = context.security_summary or {}
    cost = context.cost_estimate or {}
    facts: list[IntelligenceObservedFactRead] = [
        IntelligenceObservedFactRead(
            id="fact-arch-size",
            fact=f"Architecture has {len(context.resources)} resources, {len(context.relationships)} relationships, {len(context.resource_groups)} resource groups, and {len(context.subscriptions)} subscriptions.",
            source="architecture_graph",
            evidence=f"resources={len(context.resources)}, relationships={len(context.relationships)}",
            confidence=0.99,
        )
    ]

    if monitoring:
        facts.append(
            IntelligenceObservedFactRead(
                id="fact-monitoring-state",
                fact=f"Monitoring state is '{monitoring.get('state')}' with {int(monitoring.get('live_resources') or 0)} live of {int(monitoring.get('total_resources') or 0)} total resources.",
                source="monitoring_summary",
                evidence=f"state={monitoring.get('state')}, live={monitoring.get('live_resources')}, total={monitoring.get('total_resources')}",
                confidence=0.95,
            )
        )

    if incidents:
        facts.append(
            IntelligenceObservedFactRead(
                id="fact-incidents",
                fact=f"Incident adapter reported {int(incidents.get('incident_count') or 0)} incidents from current monitoring signals.",
                source="incident_summary",
                evidence=f"critical={incidents.get('critical_count')}, high={incidents.get('high_count')}",
                confidence=0.94,
            )
        )

    if security:
        facts.append(
            IntelligenceObservedFactRead(
                id="fact-security",
                fact=f"Security summary risk level is '{security.get('risk_level')}' with critical={int(security.get('critical_count') or 0)} and high={int(security.get('high_count') or 0)} findings.",
                source="governance_security",
                evidence=f"secrets={security.get('secrets_count')}",
                confidence=0.93,
            )
        )

    if cost:
        facts.append(
            IntelligenceObservedFactRead(
                id="fact-cost",
                fact=f"Estimated monthly cost is {cost.get('total_monthly_cost')} from source '{cost.get('pricing_source')}'.",
                source="cost_estimate",
                evidence=f"actual_available={(context.actual_cost or {}).get('available')}",
                confidence=0.9,
            )
        )

    return facts


def _build_incident_correlations(context: IntelligenceContext) -> list[IntelligenceIncidentCorrelationRead]:
    incident_summary = context.incident_summary or {}
    correlations: list[IntelligenceIncidentCorrelationRead] = []
    for item in (incident_summary.get("incidents") or []):
        if not isinstance(item, dict):
            continue
        state = str(item.get("monitoring_state") or "unknown")
        correlations.append(
            IntelligenceIncidentCorrelationRead(
                incident_id=str(item.get("incident_id") or ""),
                title=str(item.get("title") or "Monitoring incident"),
                severity=str(item.get("severity") or "medium"),
                status=str(item.get("status") or "open"),
                resource_name=item.get("resource_name"),
                monitoring_state=item.get("monitoring_state"),
                correlation_reason=f"Incident derived from monitoring state '{state}' for resource signal correlation.",
                recommended_action="Validate monitoring state, dependency health, and implement targeted remediation before changing architecture design.",
            )
        )
    return correlations[:30]


def _build_rca_entries(context: IntelligenceContext) -> list[IntelligenceRcaRead]:
    resources_by_id = {str(item.get("id")): item for item in context.resources if isinstance(item, dict)}
    relationships = [item for item in context.relationships if isinstance(item, dict)]
    incident_summary = context.incident_summary or {}

    entries: list[IntelligenceRcaRead] = []
    for idx, incident in enumerate((incident_summary.get("incidents") or []), start=1):
        if not isinstance(incident, dict):
            continue
        resource_id = str(incident.get("resource_id") or "")
        resource_name = str(incident.get("resource_name") or resources_by_id.get(resource_id, {}).get("name") or "unknown-resource")
        symptom = str(incident.get("message") or incident.get("monitoring_state") or "Resource health/monitoring anomaly")
        state = str(incident.get("monitoring_state") or "")

        dependency = None
        for rel in relationships:
            source = str(rel.get("source_resource_id") or "")
            target = str(rel.get("target_resource_id") or "")
            if source == resource_id and target in resources_by_id:
                dependency = str(resources_by_id[target].get("name") or target)
                break
            if target == resource_id and source in resources_by_id:
                dependency = str(resources_by_id[source].get("name") or source)
                break

        probable_cause = "Monitoring configuration gap or upstream dependency issue"
        if state in {"authentication_failure", "permission_failure"}:
            probable_cause = "Azure authentication/permission issue prevented reliable telemetry access"
        elif state == "azure_api_failure":
            probable_cause = "Azure API telemetry query failed for the resource or its dependencies"
        elif state == "not_configured":
            probable_cause = "Telemetry integration not configured for this resource path"
        elif state == "live" and str(incident.get("health_status") or "").lower() in {"degraded", "unavailable", "unhealthy"}:
            probable_cause = "Resource or related dependency health degradation under live monitoring"

        evidence = [
            f"Incident severity={incident.get('severity')} status={incident.get('status')}",
            f"Monitoring state={state or 'unknown'}",
        ]
        if dependency:
            evidence.append(f"Related dependency in relationship graph: {dependency}")

        entries.append(
            IntelligenceRcaRead(
                id=f"rca-{idx}",
                affected_resource=resource_name,
                observed_symptom=symptom,
                related_dependency=dependency,
                probable_cause=probable_cause,
                supporting_evidence=evidence,
                impact="Potential reliability and incident response delay if unresolved.",
                recommended_action="Correlate dependency telemetry and remediate the root signal before applying architecture changes.",
                confidence=0.78,
            )
        )
    return entries[:20]


def _derive_limitations(context: IntelligenceContext, provider_state: str) -> list[str]:
    limitations: list[str] = []
    monitoring_state = str((context.monitoring_summary or {}).get("state") or "")
    if monitoring_state in {"not_configured", "authentication_failure", "permission_failure", "azure_api_failure", "no_data"}:
        limitations.append(f"Monitoring data is limited by state '{monitoring_state}'.")
    actual_available = bool((context.actual_cost or {}).get("available"))
    if not actual_available:
        limitations.append("Actual billed cost is unavailable; cost analysis is partially estimated.")
    if provider_state != "configured":
        limitations.append(f"Requested AI provider path returned state '{provider_state}', fallback analysis applied.")
    if not limitations:
        limitations.append("Analysis reflects available architecture and telemetry snapshots at generation time.")
    return limitations


def build_risks_from_findings(findings: list[IntelligenceFindingRead], source: str) -> list[IntelligenceRiskRead]:
    risks: list[IntelligenceRiskRead] = []
    for idx, finding in enumerate(findings, start=1):
        priority = _priority_from_severity(finding.severity)
        if priority not in {"high", "critical", "medium"}:
            continue
        risks.append(
            IntelligenceRiskRead(
                id=f"risk-{idx}-{finding.id}",
                title=finding.title,
                priority=priority,
                explanation=finding.rationale,
                impact=finding.description,
                source=source,
                confidence=finding.confidence,
            )
        )
    return risks


def _priority_from_severity(value: str) -> str:
    severity = str(value or "").strip().lower()
    if severity in {"critical", "high", "medium", "low"}:
        return severity
    return "medium"


def _safe_confidence(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = default
    return max(0.0, min(1.0, parsed))


def _safe_json_loads(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    stripped = text.strip()
    try:
        payload = json.loads(stripped)
        return payload if isinstance(payload, dict) else None
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", stripped)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _normalize_ai_payload(raw: dict[str, Any], source: str, context: IntelligenceContext) -> ProviderExecutionResult:
    raw_findings = raw.get("findings") if isinstance(raw.get("findings"), list) else []
    raw_recommendations = raw.get("recommendations") if isinstance(raw.get("recommendations"), list) else []
    raw_risks = raw.get("risks") if isinstance(raw.get("risks"), list) else []

    findings: list[IntelligenceFindingRead] = []
    for idx, item in enumerate(raw_findings, start=1):
        if not isinstance(item, dict):
            continue
        priority = _priority_from_severity(str(item.get("priority") or item.get("severity") or "medium"))
        title = str(item.get("title") or f"AI finding {idx}").strip()
        explanation = str(item.get("explanation") or item.get("rationale") or "No explanation provided.").strip()
        findings.append(
            IntelligenceFindingRead(
                id=f"ai-finding-{idx}",
                category=str(item.get("category") or "architecture").strip().lower(),
                severity=priority,
                title=title,
                description=str(item.get("description") or explanation),
                rationale=explanation,
                affected_resources=[str(v) for v in (item.get("affected_resources") or []) if isinstance(v, str)],
                recommendation=str(item.get("recommendation") or "Review this finding and plan remediation."),
                source=source,
                confidence=0.78,
            )
        )

    recommendations: list[IntelligenceRecommendationRead] = []
    for idx, item in enumerate(raw_recommendations, start=1):
        if not isinstance(item, dict):
            continue
        priority = _priority_from_severity(str(item.get("priority") or item.get("severity") or "medium"))
        title = str(item.get("title") or f"AI recommendation {idx}").strip()
        explanation = str(item.get("explanation") or item.get("rationale") or "No explanation provided.").strip()
        recommendations.append(
            IntelligenceRecommendationRead(
                id=f"ai-rec-{idx}",
                title=title,
                category=str(item.get("category") or "architecture").strip().lower(),
                severity=priority,
                rationale=explanation,
                recommendation=str(item.get("recommendation") or "Plan and apply controlled improvements."),
                affected_resources=[str(v) for v in (item.get("affected_resources") or []) if isinstance(v, str)],
                source=source,
                confidence=0.75,
            )
        )

    risks: list[IntelligenceRiskRead] = []
    for idx, item in enumerate(raw_risks, start=1):
        if not isinstance(item, dict):
            continue
        priority = _priority_from_severity(str(item.get("priority") or "medium"))
        risks.append(
            IntelligenceRiskRead(
                id=f"ai-risk-{idx}",
                title=str(item.get("title") or f"AI risk {idx}"),
                priority=priority,
                explanation=str(item.get("explanation") or "No explanation provided."),
                impact=str(item.get("impact") or "Potential operational impact."),
                source=source,
                confidence=0.74,
            )
        )

    if not risks:
        risks = build_risks_from_findings(findings, source)

    observed_facts: list[IntelligenceObservedFactRead] = []
    for idx, item in enumerate(raw.get("observed_facts") or [], start=1):
        if not isinstance(item, dict):
            continue
        observed_facts.append(
            IntelligenceObservedFactRead(
                id=f"ai-fact-{idx}",
                fact=str(item.get("fact") or "Observed platform signal"),
                source=str(item.get("source") or source),
                evidence=(str(item.get("evidence")) if item.get("evidence") is not None else None),
                confidence=_safe_confidence(item.get("confidence"), 0.75),
            )
        )
    if not observed_facts:
        observed_facts = _build_observed_facts(context)

    rca: list[IntelligenceRcaRead] = []
    for idx, item in enumerate(raw.get("rca") or [], start=1):
        if not isinstance(item, dict):
            continue
        rca.append(
            IntelligenceRcaRead(
                id=f"ai-rca-{idx}",
                affected_resource=str(item.get("affected_resource") or "unknown-resource"),
                observed_symptom=str(item.get("observed_symptom") or "Observed service anomaly"),
                related_dependency=(str(item.get("related_dependency")) if item.get("related_dependency") is not None else None),
                probable_cause=str(item.get("probable_cause") or "Probable dependency or configuration issue"),
                supporting_evidence=[str(v) for v in (item.get("supporting_evidence") or []) if isinstance(v, str)],
                impact=str(item.get("impact") or "Operational impact possible"),
                recommended_action=str(item.get("recommended_action") or "Review telemetry and dependency path before remediation."),
                confidence=_safe_confidence(item.get("confidence"), 0.72),
            )
        )
    if not rca:
        rca = _build_rca_entries(context)

    incident_correlations: list[IntelligenceIncidentCorrelationRead] = []
    for item in raw.get("incident_correlations") or []:
        if not isinstance(item, dict):
            continue
        incident_correlations.append(
            IntelligenceIncidentCorrelationRead(
                incident_id=str(item.get("incident_id") or ""),
                title=str(item.get("title") or "Incident correlation"),
                severity=str(item.get("severity") or "medium"),
                status=str(item.get("status") or "open"),
                resource_name=(str(item.get("resource_name")) if item.get("resource_name") is not None else None),
                monitoring_state=(str(item.get("monitoring_state")) if item.get("monitoring_state") is not None else None),
                correlation_reason=str(item.get("correlation_reason") or "Correlation inferred from architecture and monitoring context."),
                recommended_action=str(item.get("recommended_action") or "Validate incident context with dependency and telemetry evidence."),
            )
        )
    if not incident_correlations:
        incident_correlations = _build_incident_correlations(context)
    limitations = [str(item) for item in (raw.get("limitations") or []) if isinstance(item, str)]
    if not limitations:
        limitations = _derive_limitations(context, "configured")

    confidence = _safe_confidence(raw.get("analysis_confidence"), 0.76)

    return ProviderExecutionResult(
        provider=source,
        source=source,
        state="configured",
        overall_assessment=str(raw.get("overall_assessment") or "AI analysis generated advisory findings and recommendations."),
        findings=findings,
        recommendations=recommendations,
        risks=risks,
        observed_facts=observed_facts,
        rca=rca,
        incident_correlations=incident_correlations,
        analysis_confidence=confidence,
        limitations=limitations,
        message=None,
    )


class OpenAIIntelligenceProvider:
    provider_name = "openai"

    def __init__(self, api_key: str | None) -> None:
        self._api_key = (api_key or "").strip()

    async def analyze(self, context: IntelligenceContext) -> ProviderExecutionResult:
        if not self._api_key:
            return ProviderExecutionResult(
                provider=self.provider_name,
                source=self.provider_name,
                state="not_configured",
                overall_assessment=None,
                findings=[],
                recommendations=[],
                risks=[],
                observed_facts=_build_observed_facts(context),
                rca=[],
                incident_correlations=_build_incident_correlations(context),
                analysis_confidence=0.0,
                limitations=_derive_limitations(context, "not_configured"),
                message="OpenAI provider is not configured.",
            )

        base_url = (os.getenv("OPENAI_API_BASE") or "https://api.openai.com/v1").rstrip("/")
        organization = (os.getenv("OPENAI_ORGANIZATION") or "").strip()
        context_payload = compact_intelligence_context(context)

        prompt = {
            "task": "Provide advisory architecture intelligence. Never modify infrastructure.",
            "required_output": {
                "findings": [
                    {
                        "title": "string",
                        "priority": "critical|high|medium|low",
                        "category": "string",
                        "description": "string",
                        "recommendation": "string",
                        "explanation": "string",
                        "affected_resources": ["string"],
                    }
                ],
                "recommendations": [
                    {
                        "title": "string",
                        "priority": "critical|high|medium|low",
                        "category": "string",
                        "recommendation": "string",
                        "explanation": "string",
                        "affected_resources": ["string"],
                    }
                ],
                "risks": [
                    {
                        "title": "string",
                        "priority": "critical|high|medium|low",
                        "explanation": "string",
                        "impact": "string",
                    }
                ],
                "overall_assessment": "string",
                "analysis_confidence": "0.0-1.0",
                "limitations": ["string"],
                "rca": [
                    {
                        "affected_resource": "string",
                        "observed_symptom": "string",
                        "related_dependency": "string|null",
                        "probable_cause": "string",
                        "supporting_evidence": ["string"],
                        "impact": "string",
                        "recommended_action": "string",
                        "confidence": "0.0-1.0",
                    }
                ],
            },
            "context": context_payload,
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if organization:
            headers["OpenAI-Organization"] = organization

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                model = (os.getenv("OPENAI_MODEL") or "").strip()
                if not model:
                    model_response = await client.get(f"{base_url}/models", headers=headers)
                    if model_response.status_code == 401:
                        return ProviderExecutionResult(self.provider_name, self.provider_name, "authentication_failure", None, [], [], [], _build_observed_facts(context), [], _build_incident_correlations(context), 0.0, _derive_limitations(context, "authentication_failure"), "OpenAI authentication failed.")
                    if model_response.status_code == 403:
                        return ProviderExecutionResult(self.provider_name, self.provider_name, "permission_failure", None, [], [], [], _build_observed_facts(context), [], _build_incident_correlations(context), 0.0, _derive_limitations(context, "permission_failure"), "OpenAI permission denied.")
                    if model_response.status_code >= 400:
                        return ProviderExecutionResult(self.provider_name, self.provider_name, "provider_error", None, [], [], [], _build_observed_facts(context), [], _build_incident_correlations(context), 0.0, _derive_limitations(context, "provider_error"), "OpenAI model discovery failed.")
                    model_payload = model_response.json() if model_response.content else {}
                    model_items = model_payload.get("data") if isinstance(model_payload, dict) else []
                    for item in model_items if isinstance(model_items, list) else []:
                        if isinstance(item, dict) and item.get("id"):
                            model = str(item.get("id"))
                            break
                if not model:
                    return ProviderExecutionResult(self.provider_name, self.provider_name, "provider_error", None, [], [], [], _build_observed_facts(context), [], _build_incident_correlations(context), 0.0, _derive_limitations(context, "provider_error"), "OpenAI model is unavailable.")

                body = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are an architecture intelligence assistant. Return JSON only."},
                        {"role": "user", "content": json.dumps(prompt)},
                    ],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                }
                response = await client.post(f"{base_url}/chat/completions", headers=headers, json=body)
        except Exception:
            return ProviderExecutionResult(
                provider=self.provider_name,
                source=self.provider_name,
                state="unavailable",
                overall_assessment=None,
                findings=[],
                recommendations=[],
                risks=[],
                observed_facts=_build_observed_facts(context),
                rca=[],
                incident_correlations=_build_incident_correlations(context),
                analysis_confidence=0.0,
                limitations=_derive_limitations(context, "unavailable"),
                message="OpenAI provider is unavailable.",
            )

        if response.status_code == 401:
            return ProviderExecutionResult(self.provider_name, self.provider_name, "authentication_failure", None, [], [], [], _build_observed_facts(context), [], _build_incident_correlations(context), 0.0, _derive_limitations(context, "authentication_failure"), "OpenAI authentication failed.")
        if response.status_code == 403:
            return ProviderExecutionResult(self.provider_name, self.provider_name, "permission_failure", None, [], [], [], _build_observed_facts(context), [], _build_incident_correlations(context), 0.0, _derive_limitations(context, "permission_failure"), "OpenAI permission denied.")
        if response.status_code >= 500:
            return ProviderExecutionResult(self.provider_name, self.provider_name, "provider_error", None, [], [], [], _build_observed_facts(context), [], _build_incident_correlations(context), 0.0, _derive_limitations(context, "provider_error"), "OpenAI returned provider error.")
        if response.status_code >= 400:
            return ProviderExecutionResult(self.provider_name, self.provider_name, "provider_error", None, [], [], [], _build_observed_facts(context), [], _build_incident_correlations(context), 0.0, _derive_limitations(context, "provider_error"), "OpenAI request failed.")

        payload = response.json() if response.content else {}
        content = ""
        if isinstance(payload, dict):
            choices = payload.get("choices") if isinstance(payload.get("choices"), list) else []
            if choices and isinstance(choices[0], dict):
                message = choices[0].get("message") if isinstance(choices[0].get("message"), dict) else {}
                content = str(message.get("content") or "")

        decoded = _safe_json_loads(content)
        if decoded is None:
            return ProviderExecutionResult(self.provider_name, self.provider_name, "provider_error", None, [], [], [], _build_observed_facts(context), [], _build_incident_correlations(context), 0.0, _derive_limitations(context, "provider_error"), "OpenAI returned an invalid response format.")
        normalized = _normalize_ai_payload(decoded, self.provider_name, context)
        normalized.provider = self.provider_name
        return normalized


class GeminiIntelligenceProvider:
    provider_name = "gemini"

    def __init__(self, api_key: str | None) -> None:
        self._api_key = (api_key or "").strip()

    async def analyze(self, context: IntelligenceContext) -> ProviderExecutionResult:
        if not self._api_key:
            return ProviderExecutionResult(
                provider=self.provider_name,
                source=self.provider_name,
                state="not_configured",
                overall_assessment=None,
                findings=[],
                recommendations=[],
                risks=[],
                observed_facts=_build_observed_facts(context),
                rca=[],
                incident_correlations=_build_incident_correlations(context),
                analysis_confidence=0.0,
                limitations=_derive_limitations(context, "not_configured"),
                message="Gemini provider is not configured.",
            )

        base_url = (os.getenv("GEMINI_API_BASE") or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        context_payload = compact_intelligence_context(context)
        prompt = {
            "task": "Provide advisory architecture intelligence. Never modify infrastructure.",
            "required_output": {
                "findings": "array",
                "recommendations": "array",
                "risks": "array",
                "overall_assessment": "string",
            },
            "schema_hint": "Use fields: title, priority, category, description, recommendation, explanation, affected_resources, impact.",
            "context": context_payload,
        }

        body = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": "Return JSON only. " + json.dumps(prompt)
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                model = (os.getenv("GEMINI_MODEL") or "").strip()
                if not model:
                    model_response = await client.get(f"{base_url}/models", params={"key": self._api_key})
                    if model_response.status_code == 401:
                        return ProviderExecutionResult(self.provider_name, self.provider_name, "authentication_failure", None, [], [], [], _build_observed_facts(context), [], _build_incident_correlations(context), 0.0, _derive_limitations(context, "authentication_failure"), "Gemini authentication failed.")
                    if model_response.status_code == 403:
                        return ProviderExecutionResult(self.provider_name, self.provider_name, "permission_failure", None, [], [], [], _build_observed_facts(context), [], _build_incident_correlations(context), 0.0, _derive_limitations(context, "permission_failure"), "Gemini permission denied.")
                    if model_response.status_code >= 400:
                        return ProviderExecutionResult(self.provider_name, self.provider_name, "provider_error", None, [], [], [], _build_observed_facts(context), [], _build_incident_correlations(context), 0.0, _derive_limitations(context, "provider_error"), "Gemini model discovery failed.")
                    model_payload = model_response.json() if model_response.content else {}
                    models = model_payload.get("models") if isinstance(model_payload, dict) else []
                    for item in models if isinstance(models, list) else []:
                        if not isinstance(item, dict):
                            continue
                        name = str(item.get("name") or "")
                        methods = item.get("supportedGenerationMethods") if isinstance(item.get("supportedGenerationMethods"), list) else []
                        if name and "generateContent" in methods:
                            model = name.split("/", 1)[-1]
                            break
                if not model:
                    return ProviderExecutionResult(self.provider_name, self.provider_name, "provider_error", None, [], [], [], _build_observed_facts(context), [], _build_incident_correlations(context), 0.0, _derive_limitations(context, "provider_error"), "Gemini model is unavailable.")

                response = await client.post(
                    f"{base_url}/models/{model}:generateContent",
                    params={"key": self._api_key},
                    json=body,
                )
        except Exception:
            return ProviderExecutionResult(
                provider=self.provider_name,
                source=self.provider_name,
                state="unavailable",
                overall_assessment=None,
                findings=[],
                recommendations=[],
                risks=[],
                observed_facts=_build_observed_facts(context),
                rca=[],
                incident_correlations=_build_incident_correlations(context),
                analysis_confidence=0.0,
                limitations=_derive_limitations(context, "unavailable"),
                message="Gemini provider is unavailable.",
            )

        if response.status_code == 401:
            return ProviderExecutionResult(self.provider_name, self.provider_name, "authentication_failure", None, [], [], [], _build_observed_facts(context), [], _build_incident_correlations(context), 0.0, _derive_limitations(context, "authentication_failure"), "Gemini authentication failed.")
        if response.status_code == 403:
            return ProviderExecutionResult(self.provider_name, self.provider_name, "permission_failure", None, [], [], [], _build_observed_facts(context), [], _build_incident_correlations(context), 0.0, _derive_limitations(context, "permission_failure"), "Gemini permission denied.")
        if response.status_code >= 500:
            return ProviderExecutionResult(self.provider_name, self.provider_name, "provider_error", None, [], [], [], _build_observed_facts(context), [], _build_incident_correlations(context), 0.0, _derive_limitations(context, "provider_error"), "Gemini returned provider error.")
        if response.status_code >= 400:
            return ProviderExecutionResult(self.provider_name, self.provider_name, "provider_error", None, [], [], [], _build_observed_facts(context), [], _build_incident_correlations(context), 0.0, _derive_limitations(context, "provider_error"), "Gemini request failed.")

        payload = response.json() if response.content else {}
        content = ""
        if isinstance(payload, dict):
            candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
            if candidates and isinstance(candidates[0], dict):
                content_obj = candidates[0].get("content") if isinstance(candidates[0].get("content"), dict) else {}
                parts = content_obj.get("parts") if isinstance(content_obj.get("parts"), list) else []
                if parts and isinstance(parts[0], dict):
                    content = str(parts[0].get("text") or "")

        decoded = _safe_json_loads(content)
        if decoded is None:
            return ProviderExecutionResult(self.provider_name, self.provider_name, "provider_error", None, [], [], [], _build_observed_facts(context), [], _build_incident_correlations(context), 0.0, _derive_limitations(context, "provider_error"), "Gemini returned an invalid response format.")
        normalized = _normalize_ai_payload(decoded, self.provider_name, context)
        normalized.provider = self.provider_name
        return normalized


class DeterministicIntelligenceProvider:
    SOURCE = "monitorai_deterministic_intelligence"

    async def analyze(self, context: IntelligenceContext) -> ProviderExecutionResult:
        if not context.resources:
            return ProviderExecutionResult(
                provider="deterministic_fallback",
                source=self.SOURCE,
                state="configured",
                overall_assessment="No resources available for intelligence analysis.",
                findings=[],
                recommendations=[],
                risks=[],
                observed_facts=_build_observed_facts(context),
                rca=[],
                incident_correlations=_build_incident_correlations(context),
                analysis_confidence=0.72,
                limitations=_derive_limitations(context, "configured"),
                message="Create resources in Architecture Studio and rerun analysis.",
            )

        findings = self._findings(context)
        findings = sorted(findings, key=lambda item: item.id)
        recommendations = self._recommendations(context, findings)
        risks = build_risks_from_findings(findings, self.SOURCE)
        observed_facts = _build_observed_facts(context)
        incident_correlations = _build_incident_correlations(context)
        rca = _build_rca_entries(context)

        if not findings and not recommendations and not risks:
            overall = "Architecture has limited analyzable signals for intelligence checks."
        else:
            overall = self._overall_assessment(self._severity_summary(findings))

        return ProviderExecutionResult(
            provider="deterministic_fallback",
            source=self.SOURCE,
            state="configured",
            overall_assessment=overall,
            findings=findings,
            recommendations=recommendations,
            risks=risks,
            observed_facts=observed_facts,
            rca=rca,
            incident_correlations=incident_correlations,
            analysis_confidence=0.8,
            limitations=_derive_limitations(context, "configured"),
            message=None if findings else "Deterministic fallback completed with limited analyzable signals.",
        )

    def _findings(self, context: IntelligenceContext) -> list[IntelligenceFindingRead]:
        findings: list[IntelligenceFindingRead] = []
        resources = context.resources
        relationships = context.relationships

        resource_ids = {item["id"] for item in resources}
        related_ids: set[str] = set()
        for rel in relationships:
            related_ids.add(rel["source_resource_id"])
            related_ids.add(rel["target_resource_id"])

        isolated = [item for item in resources if item["id"] not in related_ids]
        if isolated:
            findings.append(
                IntelligenceFindingRead(
                    id="isolated-resources",
                    category="architecture_connectivity",
                    severity="medium",
                    title="Isolated resources detected",
                    description=f"{len(isolated)} resources have no explicit relationship links.",
                    rationale="Resources without dependencies or connections can indicate incomplete architecture design or missing dependency mapping.",
                    affected_resources=[item["name"] for item in isolated],
                    recommendation="Review isolated resources and connect them with expected dependencies or document intentional isolation.",
                    source="relationship_graph",
                    confidence=0.92,
                )
            )

        subnets = [item for item in resources if item["resource_type"] == "subnet"]
        vnet_ids = {item["id"] for item in resources if item["resource_type"] == "vnet"}
        subnets_without_vnet: list[dict[str, Any]] = []
        for subnet in subnets:
            parent_id = subnet.get("parent_resource_id")
            has_link = any(
                (rel["source_resource_id"] == subnet["id"] and rel["target_resource_id"] in vnet_ids)
                or (rel["target_resource_id"] == subnet["id"] and rel["source_resource_id"] in vnet_ids)
                for rel in relationships
            )
            if parent_id not in vnet_ids and not has_link:
                subnets_without_vnet.append(subnet)

        if subnets_without_vnet:
            findings.append(
                IntelligenceFindingRead(
                    id="subnet-missing-vnet-link",
                    category="hierarchy_consistency",
                    severity="high",
                    title="Subnet hierarchy inconsistency",
                    description=f"{len(subnets_without_vnet)} subnets are not linked to a VNet.",
                    rationale="Subnet resources should be attached to a VNet through hierarchy or relationship mapping.",
                    affected_resources=[item["name"] for item in subnets_without_vnet],
                    recommendation="Assign each subnet a VNet parent or add explicit contains/connects_to relationships to its VNet.",
                    source="resource_hierarchy",
                    confidence=0.97,
                )
            )

        monitoring = context.monitoring_summary or {}
        total = int(monitoring.get("total_resources") or 0)
        live = int(monitoring.get("live_resources") or 0)
        m_state = str(monitoring.get("state") or "")
        if total > 0 and live < total:
            findings.append(
                IntelligenceFindingRead(
                    id="monitoring-coverage-gap",
                    category="operability",
                    severity="medium" if m_state in {"live", "no_data"} else "high",
                    title="Monitoring coverage gap",
                    description=f"Only {live} of {total} resources are in live monitoring coverage.",
                    rationale="Gaps in live monitoring reduce early detection and diagnosis capability.",
                    affected_resources=[],
                    recommendation="Complete Azure monitoring configuration for uncovered resources and verify data ingestion.",
                    source="monitoring_summary",
                    confidence=0.9,
                )
            )

        security = context.security_summary or {}
        critical = int(security.get("critical_count") or 0)
        high = int(security.get("high_count") or 0)
        if critical > 0 or high > 0:
            severity = "critical" if critical > 0 else "high"
            findings.append(
                IntelligenceFindingRead(
                    id="security-posture-risk",
                    category="security_design",
                    severity=severity,
                    title="Security posture risks detected",
                    description=f"Security assessment reported critical={critical}, high={high} findings.",
                    rationale="High-severity security findings indicate architecture-level exposure requiring prioritized mitigation.",
                    affected_resources=[],
                    recommendation="Prioritize remediation of critical/high security findings and rerun security assessment.",
                    source="governance_security",
                    confidence=0.95,
                )
            )

        estimate = context.cost_estimate or {}
        items = estimate.get("items") if isinstance(estimate.get("items"), list) else []
        if items:
            sorted_items = sorted(items, key=lambda item: float(item.get("monthly_cost") or 0), reverse=True)
            top = sorted_items[0]
            total_monthly = float(estimate.get("total_monthly_cost") or 0)
            top_monthly = float(top.get("monthly_cost") or 0)
            if total_monthly > 0 and (top_monthly / total_monthly) >= 0.7:
                findings.append(
                    IntelligenceFindingRead(
                        id="cost-concentration",
                        category="cost_optimization",
                        severity="medium",
                        title="Cost concentration on single resource",
                        description=f"Top resource contributes {round((top_monthly / total_monthly) * 100, 1)}% of estimated monthly cost.",
                        rationale="High cost concentration can increase optimization potential and single-point financial risk.",
                        affected_resources=[str(top.get("name") or top.get("resource_id") or "resource")],
                        recommendation="Validate rightsizing or architecture alternatives for the dominant cost resource.",
                        source="cost_estimate",
                        confidence=0.88,
                    )
                )

        if len(relationships) > len(resources) * 3 and len(resources) >= 6:
            findings.append(
                IntelligenceFindingRead(
                    id="high-relationship-complexity",
                    category="architecture_complexity",
                    severity="low",
                    title="High relationship density",
                    description="Relationship count is significantly higher than resource count.",
                    rationale="High graph density may increase change impact and troubleshooting complexity.",
                    affected_resources=[],
                    recommendation="Review whether all relationships are necessary and remove redundant links.",
                    source="relationship_graph",
                    confidence=0.8,
                )
            )

        return findings

    def _recommendations(
        self,
        context: IntelligenceContext,
        findings: list[IntelligenceFindingRead],
    ) -> list[IntelligenceRecommendationRead]:
        by_id: dict[str, IntelligenceRecommendationRead] = {}

        for finding in findings:
            rec_id = f"rec-{finding.id}"
            by_id[rec_id] = IntelligenceRecommendationRead(
                id=rec_id,
                title=finding.title,
                category=finding.category,
                severity=finding.severity,
                rationale=finding.rationale,
                recommendation=finding.recommendation,
                affected_resources=finding.affected_resources,
                source=finding.source,
                confidence=finding.confidence,
            )

        legacy_payload = {
            "resources": [
                {
                    "type": item["resource_type"],
                    "name": item["name"],
                    "configuration": item.get("properties") if isinstance(item.get("properties"), dict) else {},
                }
                for item in context.resources
            ],
            "compliance": (context.compliance_summary or {}).get("frameworks") or [],
        }
        legacy_recs = recommend_architecture(legacy_payload).get("recommendations") or []
        confidence_map = {"high": 0.9, "medium": 0.75, "low": 0.6}
        severity_map = {
            "security": "high",
            "reliability": "medium",
            "performance": "medium",
            "cost": "low",
        }

        for idx, item in enumerate(legacy_recs):
            rec_id = f"legacy-rec-{idx + 1}"
            by_id[rec_id] = IntelligenceRecommendationRead(
                id=rec_id,
                title=str(item.get("title") or "Recommendation"),
                category=str(item.get("category") or "architecture"),
                severity=severity_map.get(str(item.get("category") or "").lower(), "low"),
                rationale=str(item.get("rationale") or "Legacy intelligence recommendation."),
                recommendation=str(item.get("suggested_change") or ""),
                affected_resources=[],
                source="legacy_ai_service",
                confidence=confidence_map.get(str(item.get("confidence") or "medium").lower(), 0.7),
            )

        recommendations = sorted(by_id.values(), key=lambda item: item.id)
        return recommendations

    @staticmethod
    def _severity_summary(findings: list[IntelligenceFindingRead]) -> dict[str, int]:
        summary = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for item in findings:
            sev = str(item.severity).lower()
            if sev in summary:
                summary[sev] += 1
        return summary

    @staticmethod
    def _overall_assessment(summary: dict[str, int]) -> str:
        if summary.get("critical", 0) > 0:
            return "Critical architecture risks detected; immediate remediation is recommended."
        if summary.get("high", 0) > 0:
            return "High-priority architecture issues detected; remediation should be planned promptly."
        if summary.get("medium", 0) > 0:
            return "Architecture is operational but has medium-priority optimization and risk findings."
        return "Architecture appears stable with low-severity or no detected risks."
