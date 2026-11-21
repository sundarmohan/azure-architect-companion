"""Adapted deterministic recommendation logic reused from legacy ai_service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal

RecommendationCategory = Literal["cost", "security", "performance", "reliability"]


@dataclass(frozen=True)
class Recommendation:
    category: RecommendationCategory
    title: str
    rationale: str
    suggested_change: str
    confidence: str = "medium"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "title": self.title,
            "rationale": self.rationale,
            "suggested_change": self.suggested_change,
            "confidence": self.confidence,
        }


def recommend_architecture(architecture_json: Dict[str, Any]) -> Dict[str, Any]:
    architecture_json = architecture_json or {}
    resources = _ensure_list_of_dicts(architecture_json.get("resources"))
    frameworks = _normalize_frameworks(architecture_json.get("compliance"))

    recs: list[Recommendation] = []
    recs.extend(_security_recommendations(resources, frameworks))
    recs.extend(_reliability_recommendations(resources, frameworks))
    recs.extend(_cost_recommendations(resources))
    recs.extend(_performance_recommendations(resources))

    seen: set[tuple[str, str]] = set()
    out: list[Dict[str, Any]] = []
    for rec in recs:
        key = (rec.category, rec.title)
        if key in seen:
            continue
        seen.add(key)
        out.append(rec.as_dict())

    return {"recommendations": out}


def _ensure_list_of_dicts(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _normalize_frameworks(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        val = str(item or "").strip().lower()
        if val == "hipaa":
            out.append("HIPAA")
        elif val in {"iso", "iso 27001", "iso27001"}:
            out.append("ISO 27001")
        elif val == "gdpr":
            out.append("GDPR")
        elif val in {"soc2", "soc 2", "soc-2"}:
            out.append("SOC 2")
    return list(dict.fromkeys(out))


def _cfg(resource: Dict[str, Any]) -> Dict[str, Any]:
    return resource.get("configuration") if isinstance(resource.get("configuration"), dict) else {}


def _security_recommendations(resources: List[Dict[str, Any]], frameworks: list[str]) -> List[Recommendation]:
    recs: list[Recommendation] = []

    if frameworks and any(str(_cfg(resource).get("logging", "")).lower() not in {"enabled", "on", "true", "yes"} and _cfg(resource).get("logging") is not True for resource in resources):
        recs.append(
            Recommendation(
                category="security",
                title="Enable centralized logging everywhere",
                rationale="Compliance frameworks require auditability and security visibility.",
                suggested_change="Set configuration.logging=enabled for all resources.",
                confidence="high",
            )
        )

    for resource in resources:
        rtype = str(resource.get("type") or "").lower()
        config = _cfg(resource)
        if rtype in {"storage", "db"} and config.get("encryption_at_rest") is not True:
            recs.append(
                Recommendation(
                    category="security",
                    title="Enforce encryption at rest for data stores",
                    rationale="Unencrypted data at rest raises risk and compliance exposure.",
                    suggested_change="Set configuration.encryption_at_rest=true for storage and db resources.",
                    confidence="high",
                )
            )
        if rtype == "db" and config.get("encryption_in_transit") is not True:
            recs.append(
                Recommendation(
                    category="security",
                    title="Require TLS for database connections",
                    rationale="Encryption in transit protects against interception.",
                    suggested_change="Set configuration.encryption_in_transit=true for db resources.",
                    confidence="high",
                )
            )

    return recs


def _reliability_recommendations(resources: List[Dict[str, Any]], frameworks: list[str]) -> List[Recommendation]:
    recs: list[Recommendation] = []
    regulated = any(item in frameworks for item in {"SOC 2", "ISO 27001", "HIPAA"})
    if not regulated:
        return recs

    for resource in resources:
        if str(resource.get("type") or "").lower() != "vm":
            continue
        config = _cfg(resource)
        autoscaling = config.get("autoscaling") is True
        try:
            min_instances = int(config.get("min_instances") or 0)
        except Exception:
            min_instances = 0
        if not autoscaling and min_instances < 2:
            recs.append(
                Recommendation(
                    category="reliability",
                    title="Add redundancy for compute",
                    rationale="Regulated systems should avoid single-instance compute points of failure.",
                    suggested_change="Enable autoscaling or set configuration.min_instances>=2 for vm resources.",
                    confidence="medium",
                )
            )
            break

    return recs


def _cost_recommendations(resources: List[Dict[str, Any]]) -> List[Recommendation]:
    recs: list[Recommendation] = []
    if any(str(resource.get("type") or "").lower() == "vm" for resource in resources):
        recs.append(
            Recommendation(
                category="cost",
                title="Consider commitment discounts for steady workloads",
                rationale="Reserved or commitment-based pricing can reduce compute spend for always-on services.",
                suggested_change="Evaluate reserved instances or savings plans for long-running compute resources.",
                confidence="medium",
            )
        )
    return recs


def _performance_recommendations(resources: List[Dict[str, Any]]) -> List[Recommendation]:
    recs: list[Recommendation] = []
    for resource in resources:
        if str(resource.get("type") or "").lower() != "db":
            continue
        config = _cfg(resource)
        if config.get("ha") is not True and config.get("multi_az") is not True:
            recs.append(
                Recommendation(
                    category="performance",
                    title="Enable HA for database in production",
                    rationale="HA reduces recovery time and improves service continuity.",
                    suggested_change="Enable HA or multi-zone deployment for database resources.",
                    confidence="medium",
                )
            )
            break
    return recs
