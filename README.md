# MonitorAI V2.20

Full-screen Azure architecture designer milestone.

## Added
- React Flow canvas
- Azure resource palette
- Full-screen design area
- Add resource nodes
- Connect resources
- Delete resources
- Rename resources
- Persist node positions
- Persist relationships
- Architecture-specific resource/relationship APIs
- PostgreSQL tables and Alembic migration for graph entities
- Existing V2.1.1 dashboard/CRUD retained

## Repository and deployment

This repository is the single home for MonitorAI V2.2 (consolidated from the
previous Azure Architect Companion repo, whose CI/CD and EC2 target it reuses).

- **CI/CD:** `.github/workflows/docker-deploy.yml`. Pull requests to `main` run backend
  tests (against a throwaway PostgreSQL service) and frontend tests and build only.
  Pushes to `main` run CI. A manual Actions run on `main` with `deploy: true`
  builds the FastAPI and Vite image, publishes it to GHCR, and deploys to EC2.
- **Production stack:** `docker-compose.yml` (app on host port `8001`, PostgreSQL with
  no host port, volume `monitorai_pg_data`). `deploy/deploy.sh` generates
  `POSTGRES_PASSWORD` into the server's `.env` on first deploy if it is missing.
- Database migrations run automatically in the app's startup hook.

## Development checklist

- [x] Phase 0: record the repository, database, deployment, and cleanup baseline.
- [x] Phase 1: local identity, revocable sessions, RBAC, audit events, client
  isolation, protected Azure architecture designs, and encrypted Azure credentials.
  [GitHub Actions verified the Phase 1 code at `f0648ba`](https://github.com/sundarmohan/azure-architect-companion/actions/runs/44926569041).
- [x] Phase 2: client-scoped Azure discovery and inventory, architecture
  lifecycle and revisions, design validation and cost estimates, and reviewable exports.
  [GitHub Actions verified the Phase 2 code at `8854402`](https://github.com/sundarmohan/azure-architect-companion/actions/runs/44927878566).
  Azure inventory tests use mocked Azure responses. Live Azure access and
  applying exported artifacts are outside this verification.
- [x] Phase 3: scoped Azure monitoring, network intelligence, and opt-in polling.
  [GitHub Actions verified the Phase 3 code at `d044e9d`](https://github.com/sundarmohan/azure-architect-companion/actions/runs/44932110082).
  Provider responses are mocked in CI. Live Azure collection remains unverified.
- [x] Phase 4: Azure cybersecurity posture, threat signals, and finding tracking.
  [GitHub Actions verified the Phase 4 code at `c6e57d1`](https://github.com/sundarmohan/azure-architect-companion/actions/runs/44941135258).
  CI uses mocked Azure responses.
- [x] Phase 5: authorized assessment records, finding imports, and retest tracking.
  [GitHub Actions verified the Phase 5 code at `791bf29`](https://github.com/sundarmohan/azure-architect-companion/actions/runs/44943078778).
  The private EC2 preview was upgraded after a preview database backup.
### Remaining development by phase

| Phase | Working foundation to reuse | Gap to close |
| --- | --- | --- |
| 1 · Identity and clients | Local accounts, tenant membership, role guards, and audit event storage in `backend/app/domains/access/`. | Account now shows recent client or platform audit activity, scoped by administrator role. CI covers tenant isolation. |
| 2 · Architecture and inventory | Architecture lifecycle, editable graph, exports, and client-scoped Azure inventory. | Design Details now compares top-level resources in a mapped subscription with its latest completed inventory, including missing, ambiguous, and stale results. Child resources need a separate matching model. |
| 3 · Monitoring and network | Scheduled Azure observations, network evidence, and diagnostics in `backend/app/domains/monitoring/`. | Monitoring exposes resource health evidence for triage. Live Azure validation remains open. |
| 4 · Security and threats | Defender inputs, posture rules, activity signals, and remediation tracking. | Triage remediation by tracking status in the current evidence snapshot. Linking findings to incident investigations remains open. |
| 5 · Assessment records | Authorized assessment scope, sanitized finding imports, deduplication, and human retest history. | Review imported findings and related Defender evidence, and record expiring risk acceptance for imported findings. Client severity deadlines apply when a finding has no explicit due date. |
| 6 · Compliance | `backend/app/domains/governance/` contains reusable design checks. The older Monitor2.0 governance reference has examples for the other frameworks. | Compliance reviews saved Azure findings by technical control area. Versioned framework mappings, recorded reviews, corrective actions, and assessment history remain open. |
| 7 · DevSecOps, alerts, and incidents | `monitoring/alert_incident_workflow.py` and `incidents/` contain persisted alert and incident building blocks. | Health evidence links to acknowledged alerts, incidents, RCA notes, and corrective actions. DevSecOps reads recent public pipeline runs and accepts sanitized repository findings. |
| 8 · Cost and recovery | `backend/app/domains/cost/` includes design estimates and Azure Cost Management parsing. | Cost queries, budgets, anomaly review, and backup evidence are active. Recovery objectives are stored by subscription. Cached Azure Advisor cost recommendations are available. End-to-end recovery testing remains open. |
| 9 · Reports and validation | `backend/app/domains/reports/` and existing report and dashboard workspaces provide reusable presentation and aggregation logic. | The active overview and reports use client-scoped evidence. Integrated browser and live Azure testing remain open. |

Older MonitorAI, Monitor2.0, and Azure Architect Companion trees are read-only
references. Product changes belong in the consolidated application. Azure is
the initial cloud integration. AWS and GCP integrations remain deferred.

GitHub Actions checks fresh PostgreSQL migrations, backend and frontend tests,
and the production frontend build. Azure integration tests use mocked provider
responses.

## Product module status

This is a source and CI inventory for the development branch. An active
workflow requires a reachable screen or API, client authorization, and usable
underlying behavior. A working core can still have coverage and live validation
gaps. Six modules have a working core and ten have partial workflows. These counts describe
module breadth rather than percent complete.

| # | Module | Status | Available behavior and remaining gap |
| --- | --- | --- | --- |
| 1 | Overview Dashboard | Partial | Overview summarizes saved inventory, health, security, recent incidents, and compliance review actions for the selected subscription. |
| 2 | Architecture Designer | Working core | Active Azure catalog and canvas, resource relationships, review and approval, revision comparison and restore, validation, cost estimates, and Terraform and Ansible downloads. Export support is bounded by resource types and options. Inventory comparison currently covers top-level resource identities. |
| 3 | Azure Cloud Management | Working core | Encrypted client connection, configured subscriptions, and stored resource inventory. Live Azure validation remains open. |
| 4 | Infrastructure Monitoring | Working core | Azure Resource Health, supported performance and capacity metrics, polling, bounded diagnostics, and health triage. Coverage depends on resource type and permissions. Persisted alerts remain open. |
| 5 | Network Intelligence | Working core | Configured topology, DNS, routes, NSGs, firewalls, exposure, and aggregate traffic counters. Flow-level attribution and effective reachability remain open. |
| 6 | Cybersecurity Engine | Partial | Configuration and IAM checks, Defender feeds where available, explainable risk, and remediation triage. Deeper identity, patch, and vulnerability coverage remains open. |
| 7 | Ethical Hacking | Working core | Authorized scope records, sanitized evidence imports, finding lifecycle, human retesting, and JSON exports. Testing and scanning are human-led outside the application. |
| 8 | Vulnerability Management | Partial | Sanitized scanner-result imports, deduplication, severity, ownership, due dates, and remediation tracking already work. The portfolio brings these records together and includes related Defender evidence. Client administrators can record expiring risk acceptance for imported findings. Client severity deadlines apply when a finding has no explicit due date. |
| 9 | Threat Detection | Partial | Selected Azure Activity patterns and Defender alerts are displayed. Saved Defender and Azure Activity signals can be correlated by exact Azure resource. Operators can link saved Security findings to an existing incident in the same subscription. |
| 10 | DevSecOps | Partial | The workspace reads recent workflow run evidence from public GitHub repositories. It also imports sanitized dependency, image, secret, Dockerfile, and IaC finding metadata. A client administrator can configure an encrypted token for one private repository. The workspace reads Dependabot alerts for the configured repository and associates imported findings with matching workflow commits. |
| 11 | Compliance Engine | Partial | The active Compliance workspace reviews saved Azure technical evidence. Supports recorded technical reviews and corrective actions. The versioned catalog includes starter controls for all four frameworks and supports manual outcomes. Review history preserves scoped decision changes. Full catalog coverage remains open. |
| 12 | Alerts & Incidents | Partial | Monitoring supports acknowledgement of saved health evidence. Operators can create linked incidents and record ownership, status, and RCA notes. Corrective and preventive actions track owners, deadlines, and status. Escalation and notifications remain open. |
| 13 | Cost Management | Partial | Design estimates, actual Azure costs, and local monthly budget comparisons are active. Daily cost anomaly review flags statistically unusual reported charges. Cached Azure Advisor cost recommendations support resource-level review. |
| 14 | Backup & DR | Partial | Backup shows bounded job, restore, protected item, and supported retention evidence from inventoried Recovery Services vaults. Site Recovery replication evidence is available for inventoried vaults. Observed recovery point age and restore duration can be compared against saved subscription targets. End-to-end recovery testing remains open. |
| 15 | Reports | Partial | Reports exports technical, security, compliance, and executive evidence summaries for a selected subscription. Full report templates, cross-subscription rollups, and scheduled delivery remain open. |
| 16 | Administration | Working core | Local accounts, multi-client workspaces, role assignment, encrypted Azure credentials, and scoped audit review. Broader policy and integration administration remain open. |

## Phase 7 monitoring alert acknowledgement

In Monitoring, review confirmed resource health evidence for the selected
Azure subscription. Editors and administrators can acknowledge a specific
saved observation. MonitorAI keeps the acknowledgement and its evidence in
the client workspace and records the action in audit history.

An acknowledgement applies to the recorded observation. Later collections can
show new evidence, and retained or incomplete snapshots still carry their
collection status. Operators can create an incident from acknowledged evidence and record its owner,
status, and RCA note. Notifications and DevSecOps
integration remain open.

## Phase 6 compliance evidence

Open Compliance and select a configured Azure subscription. The review uses
the saved Security snapshot and groups relevant technical findings by control
area. Review source, resource, and evidence before deciding whether a control
is applicable or requesting corrective action.

A matching finding is a reason to review the control area. Insufficient evidence
leaves it unable to validate. The view identifies retained and incomplete
snapshots and carries through coverage limits. A versioned starter catalog supports manual framework reviews. Review history preserves changes to decisions and corrective action status. Full catalog coverage remains open. Editors can save review decisions and corrective actions.

## Phase 5 assessment and vulnerability records

In Assessment & Vulnerabilities, record authorization references, environment,
scope, exclusions, and the time window for work performed by authorized people.
Import a JSON batch of sanitized findings from an approved tool. Repeat imports
with the same source and external ID preserve the original finding and tracking.
Move findings through confirmation, remediation, and human retest. A retest note
is required to close a finding. Reports can be exported as JSON.

The vulnerability portfolio lists imported findings across the selected
client's assessments in severity order. Review the linked assessment to
update ownership, deadlines, and retest status. Related Defender evidence
comes from the saved Security snapshot for the selected configured
subscription. Defender assessment evidence retains its source label because
it can also describe broader security posture and recommendations.

MonitorAI records and tracks assessment evidence. Assessment actions never
connect to assessment targets, trigger tests, or run scanners. Keep credentials,
personal data, and raw diagnostic outputs out of imported summaries.

## Phase 4 Azure cybersecurity and threat detection

Open Security Posture and Threats for a configured subscription with a
complete inventory. Editors and administrators can refresh evidence, and
administrators can opt in to scheduled security collection. The workspace
shows read-only configuration findings, Defender assessments and active
alerts where available, and selected Azure Activity security-control signals.
A burst of at least three failed changes of the same type on the same scope
in 24 hours is flagged for review.
Refresh Network Intelligence beforehand to include its configured exposure
evidence.

Each finding shows its evidence and suggested review action. Record an owner,
due date, and tracking status in MonitorAI. Use the tracking filters to review
outstanding work from the selected subscription. The queue reflects the
displayed snapshot and flags incomplete or retained evidence. Tracking changes affect local
records only. The risk score sums finding severity weights, capped at 100.
A score applies to available evidence and does not certify the environment.
Missing Azure permissions and unsupported sources are identified separately.

## EC2 deployment

MonitorAI serves its bundled frontend and same-origin API through Caddy.
The app listens on EC2 loopback port 8003. PostgreSQL uses a dedicated Docker
network and persistent volume without a published port.

1. In GitHub's `Dev` environment, keep `EC2_HOST`, `EC2_USER`, and
   `EC2_SSH_PRIVATE_KEY` configured. Set `MONITORAI_PUBLIC_URL` to the
   HTTPS origin assigned to MonitorAI. An optional `EC2_INSTANCE_ID` pins
   the SSH target to an approved instance.
2. On the existing EC2 host, export `MONITORAI_PUBLIC_HOST` for that origin
   and run `bash deploy/configure-ingress.sh` from the deployment files. This
   provisions the separate MonitorAI virtual host on the existing host-network
   Caddy proxy. Point the domain at EC2 before using domain HTTPS. For direct
   IPv4 HTTPS, use a stable public IPv4 and allow certificate validation on the
   existing port 80/443 ingress.
3. Push to `main`, or start the workflow manually from `main` with `deploy`
   enabled. Pull requests run CI only. Check that image publication, deployment,
   public Chromium verification, and release finalization all pass.
4. Open the configured public URL and use your existing MonitorAI credentials.
   The workflow checks the rendered sign-in screen and protected API without
   using a stored administrator password.

The deployment replaces only the MonitorAI app container. It verifies the
mounted PostgreSQL volume and runs Alembic upgrade after confirming the
candidate and current database are at the same revision. Schema-changing
releases need a separate backward-compatible migration plan before rollout.
A failed application or public browser check restores the previous app image
without downgrading or restoring the live database. If the RCA ingress is
redeployed from a different release directory, reapply the MonitorAI virtual
host to that active Caddy configuration.

## Phase 3 Azure monitoring and network intelligence

Refresh Azure Inventory for the subscription before collecting observations.
Editors and administrators can refresh either workspace. Client administrators
can opt in to polling from Infrastructure Monitoring. The schedule collects
both telemetry and network snapshots for the selected subscription, at
intervals from five minutes to 24 hours.

Infrastructure Monitoring shows Azure Resource Health and supported Azure
Monitor hourly metric points from the previous 24 hours. A refresh samples up
to 40 inventoried resources. Network Intelligence displays configured links
and evidence such as network and DNS relationships, route tables, network
security groups, firewall configuration and attached public IPs. Traffic
information comes from supported Azure Monitor aggregate counters. Effective
reachability, packet capture and flow-level attribution are outside this
release.

Observations show when the latest attempt and successful collection occurred.
The UI identifies deliberately retained earlier data after a failed collection.
Client credentials and subscriptions determine collection scope. All provider
calls are read-only.

### Resource health triage

Open Monitoring and select a subscription with a saved observation. The
triage view uses confirmed Degraded and Unavailable responses from Azure
Resource Health. Open a listed resource to inspect its collected health and
metrics. An earlier snapshot retained after a failed refresh is identified
as historical evidence. Unsupported and inconclusive health readings leave
coverage incomplete.

Development and CI use mocked Azure responses. For live validation, configure
a read-only connection for the intended validation subscription in MonitorAI
under Azure Connection, then refresh Azure Inventory and Monitoring.

### Advanced Diagnostics

Editors and administrators can query hourly log counts for an inventoried
resource and a 1, 6, 24, or 72-hour window. Sources include exported Azure
Activity, AzureDiagnostics, App Service HTTP logs, Application Insights
exceptions, and Linux Syslog or Windows Event logs sent to Azure Monitor.
Select the Application Insights resource for application exceptions. A
customer administrator must configure diagnostic routing or the Azure Monitor
Agent and grant resource-context log read permissions beforehand. An empty
result may reflect ingestion delay, an unconfigured source, or filtered access.
MonitorAI stores an audit event, while log query results are displayed on demand.

Azure CLI and PowerShell can query the same data independently using Azure
operator credentials. MonitorAI sends fixed KQL through the resource-scoped
Logs API. Existing host and App Service diagnostics can be routed into Azure
Monitor by customer operators. See the
[resource-context API documentation](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/api/azure-resource-queries).

## Phase 2 Azure and design workflows

A client administrator configures one Azure tenant and service principal, a
primary subscription, and up to 25 additional subscription IDs. Use a service
principal with only the required Azure read access. Refresh from Azure Inventory
to collect resource group and resource summaries for the selected subscription.
MonitorAI preserves the last complete snapshot when a refresh fails and displays
the failure and freshness separately. Inventory does not write back to Azure
or alter a design.

Architecture Studio provides project and environment filters, duplication,
revision save/compare/restore, and approval history. Submit a draft for review
and have a client administrator approve it. Return reviewed designs to draft
before editing. Approval changes only the design record.

Export architecture definition JSON, a topology SVG, Terraform JSON for
supported resource groups, virtual networks, and subnets, or an Ansible
playbook for declared Linux packages and service state. Ansible uses the
`azure_managed_hosts` inventory group, which an IT manager maps to approved
hosts separately. Exported files require review. The application never executes
these files and does not collect host login credentials.

## Phase 1 access setup

Set `MONITORAI_BOOTSTRAP_USERNAME` and `MONITORAI_BOOTSTRAP_PASSWORD` in a
protected runtime environment before the first start. The password needs at
least 12 characters. Startup creates the first platform administrator once.
Remove the bootstrap variables after setup and manage passwords through the
Account workspace.

Set `MONITORAI_AZURE_ENCRYPTION_KEY` to a Fernet key through protected runtime
configuration. Preserve that key securely across restarts. Without it, Azure
credential save and decryption fail closed. The Account workspace provides
client creation, account setup, and client role assignment. Save an Azure
service principal with read access scoped to the selected subscription.
Existing unassigned architectures and legacy credentials are preserved
in storage and require a separately approved migration to a client.

Use HTTPS for deployed sign-in. For a loopback-only split frontend/backend
development setup, explicitly set `MONITORAI_INSECURE_LOCAL_COOKIE=1` in the
backend process environment and use the same loopback hostname for both origins.
Automated checks run in GitHub Actions.

## Development Workflow (Docker PostgreSQL + Local Backend/Frontend)

Use this flow for fast local iteration while keeping production/integration compose unchanged.

### One-command unified dev startup (recommended)

From the repository root run (expects a Python virtualenv at `.venv/`):

```bash
powershell -ExecutionPolicy Bypass -File scripts/start-unified-dev.ps1
```

This enforces a single development runtime:
- Docker: PostgreSQL only (`monitorai-dev-db-1` on `localhost:55432`)
- Local: backend (`127.0.0.1:8000`) + frontend (`127.0.0.1:5173`)

Optional helpers:

```bash
# status snapshot (containers + ports + owning processes)
powershell -ExecutionPolicy Bypass -File scripts/status-unified-dev.ps1

# stop local backend/frontend only (keeps Docker DB running)
powershell -ExecutionPolicy Bypass -File scripts/stop-unified-dev.ps1
```

1) Start PostgreSQL only (isolated dev DB):

```bash
docker compose -p monitorai-dev -f docker-compose.dev-db.yml up -d
docker compose -p monitorai-dev -f docker-compose.dev-db.yml ps
```

2) Run backend locally (from `backend/`):

```bash
# PowerShell
$env:DATABASE_URL="postgresql+asyncpg://monitorai:monitorai_dev@localhost:55432/monitorai"
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

3) Run frontend locally (from `frontend/`):

```bash
# PowerShell
$env:VITE_API_URL="http://localhost:8000/api"
npm run dev -- --host 127.0.0.1 --port 5173
```

The root `docker-compose.yml` is the production/EC2 stack and pulls the published
image; it is not used for local development.

## Important
This milestone establishes the designer foundation. Dependency auto-placement, Azure live import, Azure subscription connection, compliance, cost, Terraform and AI are deliberately subsequent milestones.


## V2.2.2
- Resource palette supports native drag-and-drop into the canvas.
- Click-to-add remains available as a fallback.
- Added favicon to remove `/favicon.ico` browser 404 noise.


## V2.3 — Azure hierarchy foundation
- Multiple Azure subscriptions per architecture
- Multiple resource groups per architecture
- Resource group location captured independently
- Dependency metadata model
- Hierarchy APIs and designer panel
- Existing full-screen canvas retained
- No forced deployment or compliance lock-in


## V2.4 — Visual Azure hierarchy and dependency foundation
- Resource Groups render as visual canvas containers.
- Resources can be assigned to a Resource Group and displayed inside it.
- Multiple Resource Groups and locations supported.
- Subscription association supported.
- Resource Group is automatically created for the first resource when none exists.
- Dependency suggestions for common Azure resource prerequisites.
- Drag/drop and click-to-add retained.


## V2.4.1 — stability fix

This patch specifically addresses the V2.4 runtime errors seen with an existing Docker
PostgreSQL volume:

- CORS explicitly allows localhost and 127.0.0.1 frontend origins.
- Existing databases are upgraded idempotently at application startup.
- Missing `resource_group_id` and `subscription_id` columns are added without deleting data.
- Required foreign keys/indexes are created safely.
- React Flow drag/drop now uses `screenToFlowPosition()` instead of browser-pixel
  calculations, so dropped resources use the actual canvas coordinates.
- Click-to-add remains available.
- No destructive database reset is required.

### Start

```bash
docker compose down
docker compose up --build
```

If an old development container is still serving cached frontend assets, rebuild with:

```bash
docker compose build --no-cache frontend backend
docker compose up
```

## V2.4.4 - stabilization baseline
- React Flow drop coordinates now use flow-space conversion with zoom/pan support.
- Resource and Resource Group positions persist and reload from database values.


## V2.19 - Complete incidents and alerts operational workflow
- Monitoring signals now sync into persistent operational alerts.
- Alerts are correlated to persistent incidents using the existing legacy incident engine adapter.
- Incident lifecycle transitions are supported: open, acknowledged, resolved.
- Incident timelines are persisted and appended with lifecycle events.
- Monitoring workspace adds operational views for alert summary, incident detail, and timeline.
- Existing architecture/monitoring/intelligence/report flows remain additive and compatible.
- Resource Group update/delete APIs and ownership validation added.
- Cross-architecture reference validation returns deterministic 4xx errors.
- Relationship duplication is prevented and existing duplicates are cleaned during migration.
- Dependency metadata is served from backend defaults (no conflicting frontend taxonomy).
- Startup schema strategy is migration-authoritative via Alembic upgrade.

### Migration reference note
- The V2.19 migration file is named `0008_v219_incident_alert_workflow.py`.
- Its authoritative Alembic revision id is `0008_v219_incident_alert_ops`.
- Runtime/current-head checks must use the revision id value above.

## V2.5 - Azure architecture intelligence foundation
- Backend-driven Azure resource catalog API with categories and dependency metadata.
- Expanded Azure resource coverage including SQL Server, Container Apps Environment, Public IP, NAT Gateway, VPN Gateway, Bastion, Private Endpoint, and Log Analytics Workspace.
- Visual hierarchy foundation: Resource Group container, VNet containers, Subnet containers, and nested resource context.
- Dependency workflow on resource drop with required vs optional dependency guidance.
- Relationship validation endpoint to prevent invalid relationship types between resources.
- Relationship types expanded: connects_to, contains, depends_on, deployed_in, integrated_with (selected by backend validation, no permanent top selector UI).
- Resource editing currently uses existing actions (rename, move, save layout); no permanent right-side Properties panel is implemented in this milestone.
- Hierarchy and position persistence includes resource parent relationships.

## V2.6 - Cost intelligence foundation (additive)
- Added an additive endpoint: `POST /api/architectures/{architecture_id}/cost-estimate`.
- Added an additive endpoint: `POST /api/architectures/{architecture_id}/actual-cost`.
- Primary pricing source: Microsoft Azure Retail Prices API (estimated/planned cost).
- Fallback pricing source: schema fallback metadata (`backend/app/domains/cost/azure.json`) when live pricing rows are unavailable.
- Response source labeling is explicit:
  - `pricing_source = "azure_retail_prices"` for full live pricing.
  - `pricing_source = "schema_fallback"` when any fallback pricing is used.
- Actual cost source labeling is explicit:
  - `pricing_source = "azure_cost_management"` for billed/spend path.
- Resource-level output includes resource type, region, SKU (when available), meter, unit, monthly and annual estimate, currency, and warnings/errors.
- Estimated cost aggregation includes resource type, Resource Group, subscription, and architecture total.
- Estimates are computed dynamically from existing architecture/resource/resource-group data. No new database tables are required.

### Estimated vs Actual cost semantics
- Estimated path: Microsoft Azure Retail Prices API (+ controlled schema fallback).
- Actual path: Azure Cost Management API.
- Actual path does not silently fall back to estimated values.
- Subscription ownership is enforced for actual cost queries.

### Normalization assumptions
- Supported unit normalization for monthly estimates:
  - Hour -> `hourly * 730`
  - Month -> `monthly`
  - Day -> `daily * 30`
  - GB-based units -> `per_gb * quantity`
- Unsupported units are not silently fabricated; controlled warnings/errors are returned.

### Limitations
- Some resources may return `pricing unavailable` if required metadata (service/SKU/unit) cannot be mapped safely.
- Fallback values are not live billing and are clearly labeled as `schema_fallback`.
- Live actual cost responses require configured Azure credentials and Cost Management permissions.

## V2.7 - Azure live resource discovery (additive)
- Added additive endpoint: `POST /api/architectures/{architecture_id}/discover-resources`.
- Discovery runs for a selected architecture-owned subscription and validates subscription ownership.
- Controlled discovery states:
  - `configured_connected`
  - `not_configured`
  - `authentication_failure`
  - `permission_failure`
  - `azure_api_failure`
- Live Azure discovery normalizes supported resources into existing MonitorAI resource model and hierarchy.
- Supported discovery mappings include: Resource Groups, VNets, Subnets, NSGs, Public IPs, NAT Gateway, Azure Firewall, Application Gateway, App Service, App Service Plan, Storage Account, SQL Server/Database, VM, Container Apps, Container Apps Environment, AKS, Key Vault, VPN Gateway, Bastion, Private Endpoint, and Log Analytics.
- Duplicate safety for repeat discovery uses Azure resource IDs scoped to architecture/subscription context.
- Discovery updates/creates matching discovered resources and resource groups without deleting manual resources absent from Azure responses.
- Designer received minimal additive controls: subscription selector, discover action, loading state, success summary, and controlled error display.

## V2.8 - Azure monitoring and health intelligence (additive)
- Added additive endpoint: `POST /api/architectures/{architecture_id}/resources/{resource_id}/monitoring`.
- Added additive endpoint: `POST /api/architectures/{architecture_id}/monitoring-summary`.
- Reuses discovered `azure_resource_id` for resource identity and never fabricates live metrics.
- Controlled monitoring states:
  - `live`
  - `not_configured`
  - `authentication_failure`
  - `permission_failure`
  - `azure_api_failure`
  - `no_data`
  - `unsupported`
- Normalized live output includes health status and time-windowed metric series when available.
- Designer received minimal additive controls: resource-level Monitoring/Health action, loading state, compact monitoring banner, and architecture live summary snippet.
- Existing hierarchy, drag/drop, relationships, save-layout, cost, and discovery workflows are retained.

## V2.13 - Settings and provider configuration foundation (additive)
- Added Settings workspace in the existing platform shell navigation.
- Added backend-owned provider key configuration for OpenAI and Gemini.
- Provider keys are accepted by backend endpoints and are never returned in API responses.
- Added provider status and connection test endpoints with controlled states:
  - configured
  - not_configured
  - authentication_failure
  - permission_failure
  - provider_error
- Added Azure integration status/test endpoints that reuse existing Azure credential/authentication patterns.
- Azure status returns controlled not_configured when credentials are absent and does not fake successful connectivity.
- Added future provider contract metadata for V2.14 compatibility:
  - openai
  - gemini
  - deterministic_fallback

## V2.14 - Real AI intelligence provider integration (additive)
- Intelligence endpoint now supports provider abstraction with OpenAI, Gemini, and deterministic fallback.
- Provider selection priority:
  - Explicit provider from request when configured/available.
  - Other configured provider.
  - Deterministic fallback.
- Controlled provider states are normalized and safe:
  - configured
  - not_configured
  - authentication_failure
  - permission_failure
  - provider_error
  - unavailable
- Intelligence response contract includes stable fields:
  - status
  - source
  - provider
  - findings
  - recommendations
  - risks
  - generated_at
  - controlled error_state when fallback occurs
- AI output is advisory-only and does not mutate architecture/resources/relationships/cost/configuration state.
- Existing V2.13 settings APIs are reused for provider secrets and status, with backend-owned secret handling retained.

## V2.15 - Executive reports workspace and API (additive)
- Added Reports workspace implementation in existing platform navigation (replacing placeholder-only behavior).
- Added additive endpoint: `POST /api/reports/architectures/{architecture_id}/executive-summary`.
- Report aggregates existing platform engines without introducing parallel logic:
  - Monitoring summary (Azure Monitor adapter states)
  - Incident summary (legacy incident engine adapter)
  - Estimated cost (Azure Retail Prices with existing fallback semantics)
  - Actual cost (Azure Cost Management with controlled unavailable state)
  - Governance compliance and security summaries
  - Intelligence analysis (OpenAI/Gemini/deterministic fallback contract)
  - Settings provider/azure status snapshot
- Added JSON export action in Reports workspace for generated report payload.
- No new PostgreSQL tables are introduced for reports; data is assembled from existing persisted architecture/settings state and live service calls.

## V2.16 - Complete live intelligence and RCA workflow (additive)
- Extended existing intelligence response contract with explicit analysis structures:
  - observed_facts
  - rca
  - incident_correlations
  - analysis_confidence
  - limitations
- Reused existing monitoring, incident, cost, governance/security, and relationship context to produce deterministic and provider-assisted RCA/correlation outputs without introducing parallel engines.
- Added consolidated architecture-context compaction for intelligence provider execution:
  - architecture graph summary
  - monitoring failure signals and coverage summary
  - incident summary and incident items
  - cost concentration summary
  - governance/security findings summary
- Added deterministic fallback derivation for observed facts, incident correlation, and RCA entries when AI providers are unavailable or return controlled errors.
- Preserved controlled provider and Azure availability states end-to-end (not_configured/authentication_failure/permission_failure/provider_error/azure_api_failure) with no fabricated live data.
- Intelligence workspace now surfaces V2.16 outputs in dedicated sections:
  - Analysis Confidence
  - Observed Facts
  - Root Cause Analysis (RCA)
  - Incident Correlation
  - Limitations
- Existing platform boundaries and prior milestones (V2.1 to V2.15) remain additive and intact.

## V2.17 - Core operational workflow coherence (additive)
- Kept existing workspace boundaries and existing engines/adapters unchanged.
- Intelligence workspace now includes a minimal `Pipeline Data Sources` summary to make analysis lineage explicit for:
  - Architecture
  - Monitoring
  - Incidents
  - Security/Governance
  - Cost
  - AI provider/fallback state
- This uses existing intelligence output fields only (observed facts, findings/recommendations/risks sources, RCA/correlations, limitations, provider/error_state) and does not introduce a new engine.
- Reports continue to consume the same integrated intelligence context through the existing V2.15 report service pipeline.
