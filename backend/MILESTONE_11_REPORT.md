# Milestone 11 Report: Conformance and Drift Detection

## Status

IMPLEMENTED locally. Runtime test execution and live Azure verification were not available in this environment.

## Architecture

M11 compares the selected immutable canonical architecture version with one immutable normalized M10 Azure intelligence snapshot. It does not call Azure, parse Terraform files, execute Terraform, or remediate differences.

The comparison pipeline bulk-loads desired resources, relationships, dependencies, and catalog declarations, normalizes Azure snapshot records once, indexes both sides, and compares them in approximately O(D + A).

## Canonical Desired Model

Desired state comes exclusively from M1/M8 `ArchitectureVersion` resources, hierarchy, relationships, and dependencies. Stable `resource_key` is the primary semantic identity. M8's deterministic architecture snapshot hash is recorded on every assessment.

First-class desired fields are resource type, name, location, SKU, tags, and hierarchy. Additional configuration is compared only when declared under catalog metadata `conformance.properties`, with a property path, category, and optional severity.

## Canonical Actual Model

M11 consumes only persisted M10 `AzureIntelligenceSnapshot.resources`. It normalizes a safe subset: resource key, Azure resource ID, type/provider, name, location, SKU, tags, selected properties, parent/resource group, relationships, dependencies, and evidence source.

Missing fields remain unavailable evidence. M11 never treats absent Azure properties, relationships, or dependencies as conformant.

## Correlation

Correlation is deterministic and ordered:

1. Exact explicit resource key from normalized evidence or the controlled resource-key tag.
2. Exact recorded Azure resource ID from canonical metadata.
3. Unique exact resource type plus resource name.
4. Otherwise `UNKNOWN` when candidates are ambiguous, or `MISSING` when no candidate exists.

Database UUIDs and fuzzy matching are not used. Correlation does not require locations to match, allowing location drift to be detected after identity is established.

## Normalization

Resource types, SKU strings, names, and location identities use case-insensitive semantic comparison. Location display names and identifiers resolve through M10's normalized location records; meaningful region differences remain visible. Dictionaries remain key-aware and lists remain ordered unless the catalog defines a future specialized comparator.

Secret-keyed properties compare presence only. Their values are replaced with `SECRET_VALUE_REDACTED` before persistence or response.

## Drift Detection

Resource outcomes are `CONFORMANT`, `MODIFIED`, `MISSING`, `UNEXPECTED`, and `UNKNOWN`. Categories are configuration, resource, hierarchy, relationship, dependency, tag, location, SKU, security, network, monitoring, and backup drift.

Tag findings distinguish `MISSING_TAG`, `UNEXPECTED_TAG`, and `TAG_VALUE_CHANGED`. Unexpected tags are informational rather than universally blocking. Desired and unexpected normalized relationship/dependency evidence is compared symmetrically.

## Conformance Status

- `CONFORMANT`: no meaningful differences or unresolved evidence.
- `DRIFTED`: one or more deterministic differences and no unknown resources.
- `PARTIAL`: deterministic differences plus unresolved evidence.
- `UNKNOWN`: unresolved evidence without deterministic drift.
- `ERROR`: assessment could not complete.

`UNKNOWN` is never converted into conformance or drift.

## Evidence

Every finding records a deterministic finding key, semantic resource identity, drift category, severity, status, safe desired/actual values, property path, explanation, M10 snapshot identity, retrieval timestamp, and Azure resource ID where available.

## Historical Assessments

Every explicit run creates a new immutable assessment. Equivalent desired and actual hashes under the same engine version produce the same comparison hash without reusing the database record. Historical comparison reports new, resolved, and persistent drift by semantic finding identity.

Audit events record `CONFORMANCE_STARTED`, `CONFORMANCE_COMPLETED`, `CONFORMANCE_FAILED`, `DRIFT_DETECTED`, and `DRIFT_RESOLVED`. The migration deliberately blocks downgrade until conformance history is exported or archived.

## M10 Integration

M11 uses M10's configured-subscription snapshot lookup and never owns Azure credentials or SDK clients. Cross-subscription snapshots are rejected. Snapshot unavailability is a normalized application error.

## M6 and M7 Integration

M11 does not regenerate Terraform. An optional M7 execution reference must belong to the selected architecture version; M11 records its M6 generation hash, M7 plan hash, execution ID, and execution state as correlation evidence. Terraform state is not treated as proof of Azure conformance.

## M8 Integration

The selected architecture version and deterministic M8 snapshot hash define desired state. M11 does not duplicate version-to-version comparison.

## M9 Integration

A fifth analysis tab renders backend assessment status, version-scoped history, M10 snapshot selection/freshness, summary counts, safe findings, and backend-computed historical comparison. React performs no normalization, correlation, or drift decisions.

## Database Migration

`006_conformance.py` follows `005_azure_resource_intelligence` and creates:

- `conformance_assessments`
- `conformance_findings`
- `conformance_events`

Foreign keys reference architecture, architecture version, M10 snapshot, and optional M7 execution. There are no M10 snapshot duplicates.

## Security

M11 exposes no Azure client, write, Terraform, shell, deployment, remediation, or arbitrary URL operation. Snapshot access remains constrained to the configured M10 tenant/subscription. Findings and audit records recursively redact secret-bearing fields and never persist raw credentials or tokens.

## Performance and Concurrency

Desired and actual resources are bulk-loaded and indexed for linear matching. Relationships, dependencies, and catalog metadata are also bulk-loaded. A process-scoped lock plus database row lock serializes assessments for the same architecture/version/snapshot while still creating a distinct immutable record for every explicit run.

## Tests

Mocked tests cover all requested resource states and drift categories, location aliases, SKU/tags/catalog properties, hierarchy, relationships, dependencies, unknown evidence/correlation, secret handling, empty and multiple-resource architectures, multiple snapshots, deterministic hashes, immutable records, history evolution, audit events, unavailable snapshots, isolation, wrong versions/architectures, M6/M7 evidence, concurrency, API errors, and prohibited operation surfaces.

- Authored: 41 M11 backend test functions covering 49 parameterized scenarios, plus 2 focused frontend tests
- Collected: not collected because no usable Python/Node runtime is installed
- Executed: 0
- Passed: not claimed
- Failed: not claimed

## Runtime Verification

Static editor diagnostics pass for M11 source and tests. The local `python` command is only an unusable Windows Store alias, and Node/npm are absent.

Azure runtime verification was not performed because no live Azure credentials/subscription were available.

## Known Limitations

- Live M10 Resource Graph discovery currently provides sparse common fields. Provider-specific security, network, monitoring, backup, relationship, and dependency facts remain `UNKNOWN` until M10 normalizers supply them.
- Terraform state resource-address mappings are not currently persisted by M7, so M11 records generation/plan identities but cannot use state mappings for correlation.
- Concurrency uses a database row lock and process lock; a dedicated PostgreSQL advisory lock may be preferable at higher distributed scale.
- Historical comparisons are version-scoped. Comparing different desired architecture versions remains M8's responsibility.

## M11 Readiness

The core architecture is ready for dependency installation, migration, mocked test execution, and final read-only Azure integration verification. M12 and automatic remediation were not implemented.
