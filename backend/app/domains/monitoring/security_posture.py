"""Deterministic posture checks built on scoped Azure management-plane evidence."""

import asyncio
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import quote

import httpx

from .security_collector import collect_security, object_fields, read_feed, subscription_resource_id

ARM = "https://management.azure.com"
PROFILES = {
    "microsoft.storage/storageaccounts": ("2023-05-01", ""),
    "microsoft.keyvault/vaults": ("2023-07-01", ""),
    "microsoft.sql/servers": ("2023-08-01", ""),
    "microsoft.sql/servers/databases": ("2023-08-01", "/transparentDataEncryption/current"),
}
WEIGHTS = {"critical": 30, "high": 15, "medium": 7, "low": 2, "informational": 0}
PRIVILEGED_ROLES = {
    "8e3af657-a8ff-443c-a75c-2fe8c4bcb635": "Owner",
    "18d7d88d-d35e-4fb3-a5c3-7773c20a72d9": "User Access Administrator",
    "f58310d9-a9f6-439a-9e8d-f62e7b41a168": "Role Based Access Control Administrator",
}


def control(code, title, severity, resource_id, evidence, recommendation, category, source="azure_configuration"):
    return dict(code=code, title=title, severity=severity, resource_id=resource_id, evidence=evidence,
                recommendation=recommendation, category=category, source=source)


def configuration_findings(kind, resource_id, props):
    hits = []

    def rule(matched, code, title, severity, evidence, recommendation, category):
        if matched:
            hits.append(control(code, title, severity, resource_id, [evidence], recommendation, category))

    if kind == "microsoft.storage/storageaccounts":
        rule(props.get("allowBlobPublicAccess") is True, "storage_public_blob_allowed", "Storage permits public blob access",
             "high", "Account permits public container settings; container access was not checked.",
             "Disable public blob access unless a reviewed use case requires it.", "Data protection")
        rule(props.get("supportsHttpsTrafficOnly") is False, "storage_http_allowed", "Storage allows insecure transport",
             "high", "Secure transfer required is disabled.", "Require HTTPS for storage traffic.", "Data protection")
        rule(props.get("minimumTlsVersion") in {"TLS1_0", "TLS1_1"}, "storage_legacy_tls", "Storage permits legacy TLS",
             "medium", "Minimum TLS is below TLS 1.2.", "Raise minimum TLS after validating clients.", "Data protection")
    elif kind == "microsoft.keyvault/vaults":
        rule(props.get("enablePurgeProtection") is not True, "vault_purge_unprotected", "Key Vault lacks purge protection",
             "high", "Purge protection is not enabled.", "Review and enable purge protection through change control.", "Secrets")
        rule(str(props.get("publicNetworkAccess", "")).casefold() == "enabled"
             and object_fields(props.get("networkAcls")).get("defaultAction") == "Allow",
             "vault_public_network", "Key Vault allows broad public network access", "high",
             "Public network access is enabled and the default network action is Allow.",
             "Review private endpoint and firewall restrictions. No secret values were read.", "Secrets")
    elif kind == "microsoft.sql/servers":
        rule(str(props.get("publicNetworkAccess", "")).casefold() == "enabled", "sql_public_network",
             "Azure SQL public networking is enabled", "medium",
             "Public network access is enabled; firewall reachability was not established.",
             "Review authorized clients, server firewall rules and private connectivity.", "Data protection")
    elif str(props.get("state", "")).casefold() == "disabled":
        rule(True, "sql_tde_disabled", "Database transparent data encryption is disabled", "high",
             "Azure reports transparent data encryption as Disabled.", "Review encryption requirements and enable TDE through change control.",
             "Data protection")
    return hits


def network_findings(resources, links, known):
    findings = []
    attachments = {str(link.get("source", "")).casefold() for link in links if link.get("kind") == "attached_to"}
    attachments.update(str(link.get("target", "")).casefold() for link in links if link.get("kind") == "uses_public_ip")
    for item in resources:
        resource_id = item.get("id", "")
        if resource_id.casefold() not in known:
            continue
        facts = object_fields(item.get("properties"))
        kind = item.get("type", "").casefold()
        count = facts.get("internet_inbound_allow_rules")
        if kind.endswith("/networksecuritygroups") and type(count) is int and count > 0:
            findings.append(control("nsg_external_inbound", "NSG has explicit internet inbound allow rules", "high",
                                    resource_id, [f"{count} explicit matching rules. Effective reachability was not tested."],
                                    "Review allowed source ranges, destinations and port requirements.", "Network", "azure_network_snapshot"))
        if kind.endswith("/publicipaddresses") and facts.get("assigned_addresses") and resource_id.casefold() in attachments:
            findings.append(control("public_ip_attached", "Public IP is assigned and attached", "medium", resource_id,
                                    ["An allocated public IP has a recorded attachment."],
                                    "Confirm the exposure is intended and protected.", "Network", "azure_network_snapshot"))
        if kind.endswith("webapplicationfirewallpolicies") and (
            str(facts.get("state", "")).casefold() == "disabled" or str(facts.get("mode", "")).casefold() == "detection"
        ):
            findings.append(control("waf_not_preventing", "WAF policy is not in active prevention mode", "medium", resource_id,
                                    ["Azure inventory reports detection-only or disabled operation."],
                                    "Review policy attachment and tune rules before switching to prevention.", "Network", "azure_network_snapshot"))
        if kind.endswith(("/azurefirewalls", "/firewallpolicies")) and str(facts.get("threat_intelligence_mode", "")).casefold() == "off":
            findings.append(control("firewall_threat_intelligence_off", "Firewall threat intelligence is disabled", "medium",
                                    resource_id, ["Observed configuration disables threat intelligence."],
                                    "Review the firewall threat intelligence policy.", "Network", "azure_network_snapshot"))
    return findings


async def check_configuration(http, headers, item, scope, semaphore):
    resource_id = subscription_resource_id(item.get("id"), scope)
    kind = str(item.get("type", "")).casefold()
    if not resource_id or kind not in PROFILES:
        return False, []
    segments = resource_id.casefold().split("/")
    suffix_kind = "/".join([segments[6], *segments[7::2]]) if len(segments) >= 9 else ""
    if suffix_kind != kind:
        return False, []
    version, suffix = PROFILES[kind]
    try:
        async with semaphore:
            response = await http.get(f"{ARM}{quote(resource_id, safe='/')}{suffix}", params={"api-version": version},
                                      headers=headers, follow_redirects=False)
        if response.status_code != 200:
            return False, []
        props = object_fields(response.json()).get("properties")
        if not isinstance(props, dict):
            return False, []
        return True, configuration_findings(kind, resource_id, props)
    except (httpx.HTTPError, ValueError):
        return False, []


def identity_findings(rows, scope):
    counts = Counter()
    for row in rows:
        props = object_fields(row.get("properties"))
        role = str(props.get("roleDefinitionId", "")).split("/")[-1].casefold()
        if str(props.get("scope", "")).casefold() == scope.casefold() and role in PRIVILEGED_ROLES:
            counts[PRIVILEGED_ROLES[role]] += 1
    return [control(f"subscription_privileged_roles_{role.lower().replace(' ', '_')}", f"Review direct {role} assignments",
                    "low", scope, [f"{count} direct subscription assignment(s)."],
                    "Verify business justification and consider narrower or time-limited access.",
                    "Identity", "azure_role_assignments") for role, count in sorted(counts.items())]


def finding_view(item, timestamp):
    evidence = item["evidence"]
    parts = [item["source"], item["code"], item["severity"], item["resource_id"].casefold()]
    if isinstance(evidence, dict):
        parts.extend(str(evidence.get(key, "")) for key in ("assessment_id", "operation", "status"))
        evidence = [f"{key.replace('_', ' ')}: {value}" for key, value in evidence.items()]
    finding_id = sha256("|".join(parts).encode()).hexdigest()
    return {**item, "id": finding_id, "evidence": evidence, "observed_at": timestamp,
            "category": item.get("category", "Provider evidence"),
            "recommendation": item.get("recommendation", "Review the evidence in Azure and validate before taking action.")}


async def collect_security_snapshot(subscription_id, resources, network, http, headers):
    scope = f"/subscriptions/{subscription_id}"
    candidates = [item for item in resources if str(item.get("type", "")).casefold() in PROFILES]
    semaphore = asyncio.Semaphore(6)
    (feed_status, feed_items, limits), (rbac_status, rbac_rows), configurations = await asyncio.gather(
        collect_security(subscription_id, resources, http, headers),
        read_feed(http, headers, f"{scope}/providers/Microsoft.Authorization/roleAssignments",
                  {"api-version": "2022-04-01", "$filter": "atScope()"}),
        asyncio.gather(*(check_configuration(http, headers, item, scope, semaphore) for item in candidates[:40])),
    )
    limits = list(limits)
    rbac_ok = rbac_status == "synced"
    if not rbac_ok:
        limits.append("Direct subscription role assignments were not available.")
    if len(candidates) > 40:
        limits.append("At most 40 supported storage, Key Vault and SQL resources are checked per collection.")
    if any(not ok for ok, _ in configurations):
        limits.append("Configuration evidence was unavailable for some supported resources.")
    if network:
        limits.append(f"Network findings use the saved snapshot collected at {network['observed_at']}.")
    else:
        limits.append("Refresh Network Intelligence to include saved network posture evidence.")
    limits.append("Patch and vulnerability coverage depends on Defender assessments available to this connection. Role review covers direct built-in subscription assignments only.")
    findings = [*feed_items, *identity_findings(rbac_rows if rbac_ok else [], scope),
                *(item for _, items in configurations for item in items)]
    if network:
        findings.extend(network_findings(network["resources"], network["links"], {row["id"].casefold() for row in resources}))
    read_any = feed_status in {"synced", "partial_failure"} or rbac_ok or any(ok for ok, _ in configurations) or bool(network)
    has_gaps = feed_status != "synced" or not rbac_ok or any(not ok for ok, _ in configurations)
    status = ("partial_failure" if has_gaps else "synced") if read_any else feed_status
    timestamp = datetime.now(timezone.utc).isoformat()
    records = {item["id"]: item for item in (finding_view(row, timestamp) for row in findings)}
    ordered = sorted(records.values(), key=lambda item: (-WEIGHTS[item["severity"]], item["id"]))
    if len(ordered) > 500:
        limits.append("Only the highest priority 500 findings from this collection are displayed and scored.")
        ordered = ordered[:500]
    counts = Counter(item["severity"] for item in ordered)
    factors = [{"severity": level, "count": counts[level], "weight": weight} for level, weight in WEIGHTS.items() if counts[level]]
    score = min(100, sum(row["count"] * row["weight"] for row in factors)) if read_any else None
    return status, {"findings": ordered, "score": score, "score_factors": factors}, limits
