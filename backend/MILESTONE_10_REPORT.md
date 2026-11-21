# Milestone 10 Report: Azure Resource Intelligence

## Status

IMPLEMENTED locally. Azure runtime verification has not been performed.

## Architecture

M10 adds a deterministic intelligence layer between the static Resource Catalog and Terraform generation. It collects read-only Azure facts through a finite client interface, normalizes them, creates immutable historical snapshots, and evaluates architecture versions through persisted preflight results.

The canonical architecture remains the source of truth. Azure snapshots are evidence and never redesign or mutate an architecture.

## Azure Client Abstraction

`AzureReadOnlyClient` defines only subscription, location, resource-group, Resource Graph resource, provider, resource-type, Compute SKU, and Compute usage reads. `AzureSdkReadOnlyClient` implements that protocol. No create, update, delete, deploy, provider registration, role, policy, network, secret, or arbitrary URL/path operation is exposed.

Azure SDK retry count and request timeout are bounded through configuration. SDK failures are normalized to stable application errors without returning exception internals.

## Authentication

The configured tenant and subscription define the only accessible scope. The default mode uses non-interactive `DefaultAzureCredential`, supporting managed/workload/environment identities. Optional `client_secret` mode uses `ClientSecretCredential` from runtime settings.

Client secrets, tokens, certificates, credentials, and authorization headers are neither persisted nor returned. API callers cannot replace the configured tenant/subscription.

## Resource Discovery

Explicit refresh reads normalized subscription metadata, locations, resource groups, providers/resource types, Resource Graph resources, Compute SKUs, and requested-region Compute usage. Raw Azure response objects are not the application model and are not persisted wholesale.

## Region Intelligence

Region validation compares the requested value against Azure-provided location identifiers and display names. It does not blindly remove spaces or rewrite the architecture location. Results are `SUPPORTED`, `UNSUPPORTED`, or `UNKNOWN` with source, retrieval time, and freshness.

## SKU Intelligence

SKU checks combine resource type, selected region, Azure SKU locations, capabilities, and restrictions. Missing evidence remains `UNKNOWN`. Explicit Azure location restrictions override a location match.

## Provider and API Version Intelligence

Provider namespace registration is normalized to `REGISTERED`, `NOT_REGISTERED`, or `UNKNOWN`; no provider is automatically registered. ARM resource-type metadata retains supported API versions and the Azure-returned preferred ordering without modifying Terraform configuration.

## Quota Intelligence

The client isolates Compute usage retrieval by region. Checks return `AVAILABLE`, `INSUFFICIENT`, or `UNKNOWN` with current usage, limit, required amount, and remaining amount. Missing provider-family quota evidence is never treated as available.

## Snapshot and Cache

Migration `005_azure_resource_intelligence` adds credential-free connection identities, immutable normalized snapshots, append-only preflight results, and optional Terraform execution references.

Snapshots are scoped by tenant and subscription, monotonically sequenced per connection, SHA-256 identified from canonical normalized content, and never updated by refresh. Every refresh creates a new snapshot. The default TTL is 3600 seconds and is configurable through `AZURE_INTELLIGENCE_CACHE_TTL_SECONDS`.

Every intelligence result exposes `fresh`, `freshness`, `retrieved_at`, and `expires_at`. Expired evidence is `STALE` and makes preflight `UNKNOWN`, preventing it from authorizing Azure-validated generation.

## Preflight

Preflight evaluates the actual location of each canonical resource against provider registration, resource type/region availability, SKU availability/restrictions, explicitly required SKU capabilities, and explicitly declared quota requirements. Findings reuse `ERROR`, `WARNING`, and `INFO` severity.

Results are append-only and reference both architecture version and Azure snapshot. An error produces `FAILED`; unresolved or stale evidence produces `UNKNOWN`; only established facts without blocking findings produce `PASSED`.

Each result records the deterministic M8 canonical architecture hash. M6 rejects a preflight when its Azure snapshot has expired or its architecture hash no longer matches the current draft.

## M6 and M7 Integration

M6 remains deterministic and never calls Azure. Existing callers default to `STATIC_ONLY`. `AZURE_VALIDATED` requires a matching persisted `PASSED` preflight and reports its snapshot/preflight identities.

M7 was not redesigned and never calls Azure. Workspace preparation optionally accepts a preflight identity, asks M6 for `AZURE_VALIDATED` generation, and stores the associated snapshot/preflight metadata for later plan traceability.

## M9 Integration

The existing designer gains one backend-only Azure analysis tab. It displays connection state and normalized preflight findings. React contains no Azure SDK/API logic and cannot supply a subscription or Azure endpoint.

## Security

- Read-only Azure methods only.
- No arbitrary Azure URL, path, command, or subscription input.
- Recursive secret-key redaction before snapshot persistence.
- No credentials, tokens, or authorization headers in snapshots or API responses.
- No Terraform execution in M10.
- Safe normalized API errors.
- Tenant/subscription filters on every snapshot lookup.

## Database Migration

`005_azure_resource_intelligence.py` follows revision `004_architecture_versioning`. It creates `azure_connections`, `azure_intelligence_snapshots`, and `azure_preflight_results`, then adds nullable snapshot/preflight foreign keys to `terraform_executions`. Previous migrations are unchanged.

## Tests

Mocked tests cover connection success/failures, discovery, location forms, resource types, SKUs, restrictions/capabilities, provider registration, API versions, quotas, snapshot creation/hash/history/TTL, explicit refresh, preflight outcomes, stale and unknown evidence, secret redaction, read-only surface, subscription isolation, refresh locking, error normalization, APIs, M6 modes, and M7 metadata.

Tests do not require a real Azure subscription.

- Authored: 56 M10 test functions covering 65 parameterized scenarios
- Collected: not collected because no usable Python/Node runtime is installed
- Executed: 0
- Passed: not claimed
- Failed: not claimed

## Runtime Verification

Static editor diagnostics pass for the authored source and tests. Test execution and Azure SDK calls depend on a working Python environment and installed requirements.

Azure runtime verification was not performed because no live Azure credentials/subscription were available.

## Known Limitations

- Compute SKU and usage APIs provide the first provider-specific implementation; other provider-family quota adapters return `UNKNOWN` until implemented.
- Snapshot locking is process-local plus database row locking; high-volume distributed refresh may warrant a PostgreSQL advisory lock.
- Azure-returned API-version ordering is retained; no independent lifecycle ranking is invented.
- The frontend does not trigger refresh, choose subscriptions, or expose raw discovery data.
- Live SDK compatibility, RBAC behavior, throttling headers, and correlation IDs require runtime verification against Azure.

## M10 Readiness

M10 is structurally ready for runtime installation, migration, mocked test execution, and read-only Azure verification. M11 has not been implemented and should begin only after those verification steps pass.
