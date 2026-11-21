# Milestone 8 Report: Architecture Versioning

## Status

IMPLEMENTED locally. Runtime verification has not been performed because this environment does not have a usable Python/pytest runtime.

## Existing Implementation Before M8

The canonical model already scoped `Resource`, `Relationship`, and `Dependency` records to `ArchitectureVersion`. `resource_key` was already M6's stable cross-version resource identity. Versions were empty containers created with caller-supplied strings and legacy statuses; there was no snapshot cloning, parentage, sequence constraint, canonical hash, activation lifecycle, canonical diff, version audit, duplicate-version protection, or finalized mutation guard.

M8 extends those existing concepts. It does not introduce a second canonical architecture model.

## Architecture

`ArchitectureVersioningService` owns version lifecycle operations:

- create a complete draft snapshot from a source version
- activate/finalize a changed draft
- compare two versions from the same architecture
- create a revert draft from an older snapshot
- calculate canonical snapshot hashes
- record and list version audit events

Canonical CRUD remains in the existing services. Draft-only update/delete operations complete the existing create/read API surface so a user can author changes without modifying a finalized version.

## Version Lifecycle

Supported M8 states are:

- `DRAFT`: editable candidate snapshot
- `ACTIVE`: finalized current snapshot
- `SUPERSEDED`: finalized former active snapshot
- `ARCHIVED`: finalized retained snapshot

Legacy `draft`, `validated`, and `deployed` values remain recognized for compatibility. New blank versions must start as draft. Activation finalizes the snapshot, records its hash and finalization time, and supersedes the previous active version in one transaction. A PostgreSQL partial unique index permits only one `ACTIVE` version per architecture.

## Snapshot Model

A cloned version contains independent rows for every resource, hierarchy parent reference, logical relationship, and dependency. New database UUIDs are generated and all internal references are remapped to the cloned rows. The new snapshot does not need its parent to reconstruct desired architecture state.

Version metadata includes sequence, parent version, change description, metadata, snapshot hash, finalization time, validation status, and compliance status. Derived Terraform files and raw validation/compliance results are not duplicated.

## Semantic Identity

Resources are correlated by `resource_key`, matching M6. Database UUIDs are never used for semantic comparison or hashing.

A resource rename, type change, location change, SKU change, property change, tag change, or hierarchy change is `RESOURCE_MODIFIED` when `resource_key` is unchanged. Changing `resource_key` is a removal plus an addition.

Relationships and dependencies use resource keys plus their semantic type. Duplicate semantic links are retained through deterministic occurrence indexing.

## Comparison

Canonical comparisons return deterministic categories:

- `RESOURCE_ADDED`, `RESOURCE_REMOVED`, `RESOURCE_MODIFIED`, `RESOURCE_UNCHANGED`
- `RELATIONSHIP_ADDED`, `RELATIONSHIP_REMOVED`, `RELATIONSHIP_MODIFIED`
- `DEPENDENCY_ADDED`, `DEPENDENCY_REMOVED`, `DEPENDENCY_MODIFIED`
- `HIERARCHY_CHANGED`, `PROPERTY_CHANGED`, `TAG_CHANGED`, `SKU_CHANGED`, `LOCATION_CHANGED`, `RESOURCE_TYPE_CHANGED`

The response includes stable source/target hashes and machine-generated counts. Cross-architecture comparisons are rejected.

## Hash Strategy

The SHA-256 snapshot hash is calculated from canonical JSON containing resources, hierarchy keys, relationships, and dependencies. JSON keys and collections use stable ordering. Database UUIDs, timestamps, version metadata, audit data, and execution metadata are excluded.

Secret values affect the hash but are never returned as hash input. Equivalent semantic snapshots with different database UUIDs produce the same hash.

## Immutability

All application canonical write operations resolve the owning version and call the M8 editable-state guard. `ACTIVE`, `SUPERSEDED`, `ARCHIVED`, and finalized legacy versions reject writes with `VERSION_IMMUTABLE`. Version cloning creates independent rows, so editing a draft cannot mutate its source.

Immutability is enforced at the application service boundary. Direct privileged SQL remains outside this guarantee.

## No-Change Protection

Cloning an unchanged source is allowed because a draft must exist before a user can author changes. Activation recalculates the candidate and parent hashes. If they match, activation returns `NO_CHANGES` with source version ID, candidate version ID, and snapshot hash; the draft is not finalized.

## Revert

Revert never edits history. Reverting V3 to V1 creates V4 with content semantically equivalent to V1 and parentage pointing to the current active/latest lineage. V1 remains unchanged, and V3-to-V4 comparison describes the actual rollback changes.

## API

Version APIs:

- `GET /architectures/{architecture_id}/versions`
- `GET /architectures/{architecture_id}/versions/{version_id}`
- `POST /architectures/{architecture_id}/versions`
- `POST /architectures/{architecture_id}/versions/{version_id}/activate`
- `POST /architectures/{architecture_id}/versions/{target_version_id}/revert`
- `GET /architectures/{architecture_id}/versions/{from_version_id}/compare/{to_version_id}`
- `GET /architectures/{architecture_id}/versions/{version_id}/events`

Draft resource, relationship, and dependency update/delete endpoints use the existing version-scoped route conventions.

## M6 Integration

M8 preserves `resource_key`, version-scoped canonical loading, and independent resource UUIDs. M6 remains solely responsible for validation-aware Terraform generation and generated-file comparison. No Terraform generation logic was duplicated in M8.

## M7 Integration

M7 already persists architecture ID, architecture version ID, generator version, generation hash, plan hash, and approval hashes. A V2 execution remains bound to V2 and cannot be treated as a V3 execution. Existing generation and saved-plan stale checks were not changed.

## Database Migration

`004_architecture_versioning` adds version sequence, parent, description, metadata, snapshot hash, finalization, validation/compliance status, uniqueness constraints, the sole-active partial index, and `architecture_version_events`. Existing versions receive deterministic per-architecture sequences. Upgrade and downgrade are implemented without changing migrations 001-003.

Architecture row locking plus database uniqueness constraints protect version allocation. Snapshot cloning uses one commit after all rows and audit data are flushed; failure rolls back the candidate completely.

## Audit and Security

Audit events include `VERSION_CREATED`, `VERSION_ACTIVATED`, `VERSION_REVERTED`, `VERSION_COMPARED`, and `VERSION_CREATION_FAILED`. Events contain identifiers, counts, hashes, and fixed error codes, not canonical properties or exception text.

M6's secret-key classifier is reused. Secret-bearing version metadata and obvious secret-bearing description labels are rejected. Canonical secret values remain part of the complete architecture snapshot, affect its hash, and are recursively redacted from comparisons and summaries.

## Tests

`test_architecture_versioning.py` covers snapshot completeness/isolation, all requested resource/link/hierarchy categories, no-change detection, hash behavior, immutability, sequential versions, revert, deterministic and cross-architecture comparisons, transactional rollback, database uniqueness, M6/M7 compatibility, secret redaction, audit, and API errors.

- Test functions authored: 35
- Test cases represented: 39
- Executed: no
- Passed: not claimed
- Failed: not claimed

## Runtime Verification

Static VS Code diagnostics report no errors. Tests were not executed because the local environment does not have a usable Python/pytest runtime. No Terraform command, Azure API, deployment, Git, or GitHub operation was performed.

## Known Limitations

- PostgreSQL migration and concurrency behavior require runtime integration verification.
- Application-level immutability does not prevent privileged direct database writes.
- Version comparison is loaded in bulk but remains in-memory; this prioritizes correctness over caching.
- Existing canonical resource APIs predate M8; M8 secures version diffs, hashes, summaries, metadata, descriptions, and audit events but does not redesign broader secret storage.

## M9 Readiness

M8 provides the backend version history, draft authoring, activation, comparison, revert, hash, and audit contracts required by a future frontend. M9 can begin after Python/PostgreSQL runtime verification of M8. M9 is not implemented here.
