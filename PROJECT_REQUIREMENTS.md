# Unified Multi-Cloud Infrastructure Management Platform

## Product requirements

**Primary application and repository:** MonitorAI V2.2\
**Temporary reference projects:** Older MonitorAI and Azure Architect
Companion\
**Final outcome:** One self-contained multi-cloud infrastructure
management platform retained in the V2.2 folder.

## 1. Vision

Build a centralized platform to design, deploy, monitor, secure, govern,
optimize, and report on cloud infrastructure across Microsoft Azure,
AWS, and Google Cloud Platform (GCP).

Use V2.2 as the product foundation. Selectively reuse the strongest
monitoring, network, traffic-analysis, and infrastructure-intelligence
capabilities from older MonitorAI, and the architecture designer,
resource catalog, validation, IaC, compliance, and drift capabilities
from Azure Architect Companion.

CloudArk is excluded.

## 2. Product objectives

1.  Visually design cloud infrastructure and generate deployable
    infrastructure-as-code.
2.  Monitor resources, services, networks, traffic, and security posture
    across clouds.
3.  Detect availability, performance, security, traffic, and compliance
    issues proactively.
4.  Centralize incident management, investigation, RCA, notifications,
    and remediation recommendations.
5.  Assess planned and existing infrastructure against HIPAA, SOC 2, and
    ISO technical controls.
6.  Estimate costs during design and identify optimization opportunities
    in existing environments.
7.  Provide consolidated operational and management reporting.
8.  Centralize cloud connections, AI providers, notifications,
    users/RBAC, integrations, policies, and schedules.
9.  Support future cloud providers, AI services, frameworks, and
    integrations through modular extensions.

## 3. Providers and integrations

### Cloud providers

-   Microsoft Azure
-   Amazon Web Services (AWS)
-   Google Cloud Platform (GCP)

Use provider-specific adapters/connectors so additional providers can be
added later.

### AI providers

-   Support configurable OpenAI API credentials.
-   Allow additional AI providers and compatible API endpoints.
-   Encrypt provider credentials; never expose secrets in logs or
    browser code.
-   Make AI features configurable.
-   Distinguish deterministic platform findings from AI-generated
    explanations and recommendations.

### Notifications and integrations

-   Configurable email provider, sender, recipients, and groups.
-   Extensible integrations for future ticketing, chat, security, and
    ITSM systems.
-   Connection testing and integration health visibility.

## 4. Functional requirements

### 4.1 Visual architecture designer

-   Create, edit, duplicate, version, and manage architecture designs.
-   Provide Azure, AWS, and GCP resource catalogs.
-   Drag resources onto a visual canvas.
-   Create relationships and dependencies between resources.
-   Edit resource properties through structured panels.
-   Organize resources by provider, category, and type.
-   Save and reopen designs and revisions.
-   Validate designs and show actionable validation messages.
-   Display cost estimates in the design workflow.
-   Export architecture definitions and generated IaC.
-   Support a controlled path from design to review, approval, plan, and
    deployment.

### 4.2 Infrastructure-as-code and deployment

-   Azure: Terraform.
-   GCP: Terraform.
-   AWS: Terraform and/or CloudFormation.
-   Generate modular, readable code with variables, outputs, and
    provider configuration.
-   Support environment-specific configuration (development, test,
    production).
-   Run formatting, initialization, validation, and plan checks.
-   Display planned changes and errors before execution.
-   Require authorization and explicit approval before applying changes.
-   Record generation, review, approval, rejection, and execution
    history.
-   Keep deployment execution separate from design and code generation.
-   Secure state files, credentials, and sensitive variables.

### 4.3 Multi-cloud monitoring and infrastructure intelligence

-   Connect multiple tenants, accounts, subscriptions, projects, and
    environments.
-   Discover and inventory supported cloud resources.
-   Display health, availability, status, and metrics.
-   Provide infrastructure and service dashboards.
-   Monitor compute, storage, databases, networking, and supported
    services.
-   Provide network and traffic visibility, patterns, volume, anomalies,
    and source/destination context where telemetry permits.
-   Reuse the best working monitoring, networking, traffic-analysis, and
    infrastructure-intelligence modules from older MonitorAI.
-   Filter by provider, account, environment, region, resource
    group/project, service, and time range.
-   Display telemetry freshness and collection failures.
-   Support configurable collection intervals and retention.
-   Generate evidence-based infrastructure recommendations.

### 4.4 Proactive alerting

Alert on: - Resource availability and health. - Performance and capacity
thresholds. - Network and traffic anomalies. - Security findings and
suspicious infrastructure activity. - Configuration changes. -
Compliance failures or regressions. - Backup, recovery, and certificate
issues. - Cost anomalies and budget thresholds.

Provide configurable rules, thresholds, severity, schedules, recipients,
deduplication, grouping, acknowledgement, assignment, resolution,
escalation, and audit history. Allow alerts to create or update
incidents.

### 4.5 Incident management and RCA

-   Create incidents manually or from alerts/events.
-   Capture title, description, severity, affected
    provider/environment/resources, timestamps, owner, status, and
    impact.
-   Maintain timelines of events, actions, comments, and status changes.
-   Correlate related alerts and infrastructure changes when evidence
    exists.
-   Generate structured RCA reports containing summary, impact,
    timeline, evidence, likely/confirmed cause, remediation, preventive
    actions, owner, and lessons learned.
-   Distinguish confirmed facts from hypotheses and AI suggestions.
-   Notify configured recipients by email.
-   Provide infrastructure-level recommendations.
-   Allow AI to summarize evidence and draft RCA content, with human
    review before publication or action.
-   Preserve records and audit history.

### 4.6 Compliance and governance

Initial frameworks: - HIPAA - SOC 2 - ISO standards, including relevant
ISO 27001 technical/security controls.

Requirements: - Assess proposed architectures before deployment and
existing discovered environments. - Map technical controls to cloud
configurations and evidence. - Use statuses such as Pass, Fail, Review
Required, Not Applicable, and Unable to Validate. - Show control
description, rationale, affected resources, evidence, severity/risk, and
recommended action. - Distinguish automated technical checks from policy
interpretation and manual evidence requirements. - Track findings and
remediation over time. - Support multiple providers, accounts, and
environments. - Provide framework and consolidated dashboards and
exportable reports. - Maintain assessment timestamps, versions, and
audit history. - Never claim certification or full compliance solely
from automated technical checks.

### 4.7 Cost estimation and optimization

During design: - Estimate costs based on provider, region,
configuration, usage assumptions, and available pricing data. - Show
recurring estimates, assumptions, and missing/unsupported pricing
inputs. - Compare design alternatives.

For existing environments: - Identify underutilized, oversized, idle, or
unattached resources when evidence supports it. - Highlight compute,
storage, database, network, and licensing opportunities. - Detect cost
anomalies and budget threshold breaches when billing data is
connected. - Show estimated savings, confidence, evidence, and
recommended action. - Require human approval for live-resource changes.

### 4.8 Centralized reporting

Provide reports for: - Infrastructure inventory and health. -
Monitoring, performance, network, and traffic. - Alerts, incidents, RCA,
and remediation. - Compliance posture, control gaps, and evidence. -
Cost estimates and optimization. - Architecture designs and deployment
history. - Security and governance findings. - Change history and
management actions.

Reports must support useful filters, on-screen viewing and export,
operational and management summaries, report scope/time period,
generation time, limitations, and traceability to evidence.

### 4.9 Centralized settings and administration

Provide one dedicated settings area for: - Cloud accounts, tenants,
subscriptions, projects, and credentials. - AI providers and encrypted
API keys. - Email and notification configuration, recipients, and
groups. - Users, roles, permissions, and access policies. - Integrations
and connectors. - Compliance frameworks, policies, and control
mappings. - Monitoring schedules, collection intervals, and retention. -
Alert and escalation rules. - Security and secret-management settings. -
Environment/deployment settings. - Audit and activity history.

Enforce RBAC and least privilege. Mask sensitive values, support safe
credential rotation, provide connection tests, and audit administrative
changes. Keep operational feature screens focused rather than
overloaded.

## 5. Additional infrastructure/compliance manager capabilities

Recommended modular enhancements after the core platform is stable: 1.
Change management with requester, approver, window, impact, and outcome.
2. Configuration backup and snapshots. 3. Automatically maintained
infrastructure inventory, diagrams, dependencies, and documentation. 4.
Risk register with likelihood, impact, owner, mitigation, due date, and
residual risk. 5. Automated compliance evidence collection and
retention. 6. Certificate inventory, expiry, ownership, and renewal
alerts. 7. Backup and disaster recovery governance, RPO/RTO, restore
tests, and readiness. 8. Vulnerability finding consolidation and
remediation tracking. 9. IAM/access governance, privileged access, stale
identities, and role reviews. 10. Patch posture and overdue update
tracking. 11. Capacity planning and utilization forecasts. 12. Vendor,
subscription, license usage, and renewal tracking. 13. Management action
tracker for audits, incidents, risks, and reviews.

## 6. Roles and access control

Design configurable RBAC for at least: - Platform Administrator -
Infrastructure Administrator - Monitoring/Operations Engineer -
Security/Compliance Officer - Auditor/Read-only User - Management/Report
Viewer

Permissions should be assignable by module and action (view, create,
edit, approve, execute, export, administer). Enforce authorization in
backend APIs, not only in the UI.

## 7. Non-functional requirements

### Security

-   Encrypt secrets and sensitive configuration at rest and in transit.
-   Use an approved secret store for production credentials.
-   Never commit credentials, tokens, private keys, or environment
    files.
-   Use least-privilege cloud identities and platform permissions.
-   Maintain administrative/security audit logs.
-   Validate input and protect APIs with authentication, authorization,
    and suitable rate limits.
-   Do not log sensitive data or secrets.

### Reliability

-   Handle cloud API failures, throttling, timeouts, and partial
    collection.
-   Use appropriate retries and backoff.
-   Show collection status and stale data.
-   Isolate provider failures.
-   Support backup and recovery of platform data/configuration.

### Scalability and performance

-   Support multiple cloud accounts and growing inventories.
-   Use background jobs for discovery, collection, scans, reports, and
    long-running deployments.
-   Paginate large datasets and avoid unnecessary loading.
-   Keep dashboards responsive.

### Maintainability and usability

-   Keep provider connectors, collectors, compliance rules,
    integrations, frontend, and backend modular.
-   Avoid duplicate services and APIs.
-   Support automated tests for critical logic.
-   Provide clear navigation, empty/loading/error states, setup
    guidance, and actionable findings.
-   Make destructive or production-impacting actions explicit and
    confirmable.

### Auditability

Record actor, timestamp, target, action, and outcome for important user
actions, configuration changes, deployments, approvals, incidents, and
assessments. Protect audit records from unauthorized modification.

## 8. Suggested navigation

Review against the existing V2.2 UI; avoid unnecessary redesign.
Suggested areas: 1. Overview 2. Architecture Designer 3. Cloud Inventory
4. Monitoring 5. Network & Traffic 6. Alerts 7. Incidents & RCA 8.
Security 9. Compliance & Governance 10. Cost Management 11. Reports 12.
Administration / Settings

Group related capabilities to avoid excessive top-level navigation.

## 9. Core logical data domains

Account for users/roles/permissions/audit; cloud
providers/connections/accounts/environments; resource inventory and
relationships; architecture designs and versions; IaC and deployment
executions; metrics/telemetry/network observations/collection jobs;
alert rules/events/notifications; incidents/timelines/RCA/remediation;
frameworks/controls/assessments/evidence/findings; cost
estimates/billing/budgets/optimization; AI configurations/outputs;
integrations/schedules/policies/settings.

These are conceptual domains, not a requirement to create one database
table for each item.

## 10. Acceptance criteria

The product is not ready merely because it starts or its UI loads.

-   Cloud connections can be configured and tested securely.
-   Provider-specific capabilities and connection status are clear.
-   Users can create, save, reopen, edit, and version architecture
    designs.
-   Resource catalogs load; drag/drop and relationship editing work.
-   Validation produces understandable, traceable findings.
-   IaC generation produces valid output for supported
    resources/providers.
-   Format/init/validate/plan workflows execute and report results.
-   Deployment requires authorization and explicit approval.
-   Discovery and monitoring show real data, timestamps, and collection
    health.
-   Alerts can be generated, acknowledged, assigned, resolved, and
    audited.
-   Incidents support manual and alert-based creation, timelines, and
    RCA.
-   Compliance assessments show control-level results and evidence
    limitations.
-   Cost estimates show assumptions and unsupported inputs.
-   Reports accurately represent selected scope and period.
-   Backend APIs enforce RBAC.
-   Secrets are absent from source control, logs, and browser responses.
-   Automated tests, builds, and end-to-end smoke tests pass for
    delivered scope.
-   Setup, configuration, supported capabilities, limitations, backup,
    and deployment are documented.

## 11. Delivery phases

### Phase 1 --- Consolidated foundation

Make V2.2 the sole product foundation; baseline it; selectively
integrate monitoring and architecture/IaC capabilities; resolve auth,
API, DB, and dependency conflicts; establish settings, RBAC, and audit
foundations.

### Phase 2 --- Core features

Complete cloud connections, architecture designer/catalog, provider
discovery, monitoring/network intelligence, alerts/incidents,
compliance/evidence, cost, and reporting.

### Phase 3 --- Reliability and governance

Strengthen security, RBAC, audit, secrets, error handling, provider
testing, documentation, recovery, automated tests, end-to-end tests, and
performance.

### Phase 4 --- Extended capabilities

Add the recommended manager features, additional providers, frameworks,
and integrations incrementally.

## 12. Scope boundaries

-   V2.2 is the final product foundation, repository, and deployment
    target.
-   Older MonitorAI and Azure Architect Companion are temporary source
    references.
-   CloudArk is excluded.
-   Do not merge projects wholesale.
-   Do not remove V2.2 functionality unless a replacement is verified
    and approved.
-   Do not treat placeholders as completed features.
-   Do not claim provider support until connection, retrieval, error
    handling, and tests work.
-   Do not claim compliance certification from automated technical
    checks.
-   Do not apply infrastructure changes without explicit authorization.
-   The final V2.2 project must be self-contained so both reference
    folders can be removed after verification.
