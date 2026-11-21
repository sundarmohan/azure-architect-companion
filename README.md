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
