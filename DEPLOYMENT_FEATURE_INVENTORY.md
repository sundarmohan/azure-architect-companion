# MonitorAI V2.2 deployment feature inventory

Source reviewed: `consolidation/v2.2-baseline` at `888e51fba2478ba121bd9325f465988a2646df2d`. This inventory describes the UI entry points, mounted APIs, and persistence in that source. Live Azure and EC2 behavior require deployment validation.

## Browser workspaces and backend coverage

| Workspace | Implementation available through the application | Limits |
| --- | --- | --- |
| Sign-in and Account | Local sign-in, sign-out, password change, platform administration, client creation, account setup, and client role assignment. Mounted under `/api/auth`. | A fresh database needs a bootstrap administrator. The client workspaces appear after a client is created and selected. |
| Architecture Studio | Default workspace for users with a client. React Flow designer with persisted resources, layout, relationships, Azure subscription and resource group hierarchy, catalog and dependency guidance. Provides design validation, draft/review/approval lifecycle, duplication, version history, compare/restore, and JSON, SVG, Terraform JSON, and Ansible exports. Uses `/api/architectures` and static Azure catalog APIs. | Terraform covers supported resource groups, VNets, and subnets. Ansible exports declared Linux package and service state. Exported artifacts require human review and execution. |
| Azure Connection | Configures and tests a client-scoped Azure service principal, its primary subscription, and up to 25 additional subscriptions. Credentials are encrypted in PostgreSQL. Uses `/api/settings/azure`. | Requires an Azure encryption key and customer-provided Azure read permissions. |
| Azure Inventory | Reads Azure resource groups and resources for the selected subscription. Uses `/api/azure/inventory` and its refresh endpoint. Records refresh failures and retains the last complete snapshot. | A successful refresh requires configured credentials and Azure access. Inventory remains independent from the design graph. |
| Monitoring | Shows resource health, supported Azure Monitor metric points and coverage, refresh status, and opt-in per-subscription scheduling. Advanced Diagnostics queries aggregate logs for an inventoried resource through `/api/azure/diagnostics/query`. Observation APIs are under `/api/azure/monitoring` and `/api/azure/monitoring/schedule`. | Collection samples up to 40 inventoried resources and uses supported metrics from the last 24 hours. Diagnostics depend on existing Azure log ingestion and read permissions. Capacity coverage consists of available metric evidence. |
| Network | Displays configured topology links, routes, DNS, security groups, firewall and public-IP evidence, and available aggregate traffic metrics. Uses the network observation routes under `/api/azure/network`. | Shows observable configuration and counters. Flow attribution and effective reachability remain outside the implemented coverage. |
| Security | Surfaces Azure configuration findings, a severity-weighted score, available Defender assessments and alerts, and selected Azure Activity signals. Editors and administrators can refresh evidence and track findings with owner, due date, and status. Uses `/api/azure/security` and finding tracking APIs. | Detection depends on configured Azure sources and permissions. Findings and tracking provide evidence and suggested review actions. |
| Assessments | Records authorization, environment, scope, exclusions, and time windows. Imports sanitized JSON findings with deduplication, tracks confirmation, remediation and human retest, and exports assessment JSON from the browser. Uses `/api/assessments`. | Human-led testing and approved tooling produce the source findings. Assessment operations record evidence in MonitorAI. |

## Partial and deferred capabilities

- The standalone platform dashboard, general reports, governance, cost, intelligence, and older monitoring workspace components are outside the active menu. The design details screen has an active cost-estimate API with Azure retail pricing and reference fallbacks. Actual billing, unused-resource analysis, incident timelines, alert summaries, governance summaries, and integrated RCA are present in older code, with architecture routes gated by the active router's allowlist or separate routers left unmounted.
- Azure is the only active integration. AWS is the deployment host. AWS and GCP monitoring and discovery are deferred.
- Design checks and security posture are active. Framework mapping, compliance evidence management, broader operational reporting, and backup/DR analysis remain deferred. No generative AI configuration is required for the active application.
- Audit events are persisted for selected sensitive operations and access denials. Designs expose lifecycle history and assessments expose finding history. The active UI has no standalone audit viewer.

## Authentication and storage

The backend uses Argon2 password hashes, hashed revocable session tokens, an eight-hour HTTP-only SameSite Strict cookie with Secure enabled by default, and a request header check on mutations. The selected client is validated server-side. Client memberships grant administrator, editor, or viewer access, while platform administrators have client administration access.

PostgreSQL is migration-authoritative. A fresh database applies all revisions from `0001_initial_architecture` through `0020_assessment_records`, the reviewed head.

| Revisions | Tables and schema changes |
| --- | --- |
| 0001–0012 | `architectures`, `architecture_resources`, `architecture_relationships`, `azure_subscriptions`, `azure_resource_groups`, `architecture_dependencies`, `provider_configurations`, `monitoring_incidents`, `monitoring_alerts`, and `monitoring_subscriptions`, including legacy snapshot fields. |
| 0013 | `local_accounts`, `client_workspaces`, `client_memberships`, `local_login_sessions`, `client_audit_events`, and `client_azure_connections`. Adds client ownership to architectures. |
| 0014–0016 | `design_revisions`, `design_lifecycle_events`, and `client_azure_inventory`; adds lifecycle fields and inventory failure details. |
| 0017–0019 | `azure_observations`, `azure_observation_schedules`, and `azure_security_tracking`; adds schedule generation and optional security observation polling. |
| 0020 | `security_assessments`, `security_assessment_findings`, and `security_assessment_finding_events`. |

## Runtime configuration

- `POSTGRES_DB`, `POSTGRES_USER`, and protected `POSTGRES_PASSWORD` configure the dedicated database. `DATABASE_URL` connects the app to PostgreSQL. The reviewed Compose file uses PostgreSQL 16, a dedicated `monitorai_pg_data` volume, and no published database port.
- `MONITORAI_BOOTSTRAP_USERNAME` and `MONITORAI_BOOTSTRAP_PASSWORD` create the initial administrator. `MONITORAI_AZURE_ENCRYPTION_KEY` is the persistent Fernet key for client credentials. `MONITORAI_OBSERVATION_WORKER` controls the observation worker and defaults to enabled. `MONITORAI_INSECURE_LOCAL_COOKIE` is a loopback development setting.
- The production image serves the Vite bundle and FastAPI on the same origin using relative `/api` requests. `VITE_API_URL` is a frontend build override. `FRONTEND_DIST_DIR` is a runtime override for the built frontend directory.
- FastAPI applies migrations before serving traffic. In the reviewed source, `/health` reports process status and version. A successful health response alone does not verify continuing database connectivity.

The implementation references are `frontend/src/App.jsx`, `frontend/src/workspaces/`, `backend/app/api/router.py`, `backend/app/domains/`, `backend/alembic/versions/`, `backend/app/main.py`, and `docker-compose.yml`.
