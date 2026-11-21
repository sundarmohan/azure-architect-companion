# Milestone 9 Report: React Architecture Designer

## Status

IMPLEMENTED locally. Runtime verification is pending because Node.js, npm, and frontend dependencies are unavailable in the local environment.

## Frontend Architecture

M9 is a Vite React 19 application written in strict TypeScript. It uses `@xyflow/react` for the designer and Lucide for centralized icons. Server state is represented by typed backend API models, canvas state is derived through `canvasMapper`, and controlled form state remains inside the properties panel.

No frontend state library was introduced. This keeps the first designer focused and avoids a second architecture engine.

## Canvas Model

The canvas supports pan, zoom, fit view, selection, dragging, explicit connection creation, nested nodes, multiple independent root containers, local undo/redo, manual container resizing, and parent auto-growth.

React Flow IDs use backend record IDs only as presentation references. Resources, relationships, dependencies, hierarchy, and configuration remain backend canonical records.

Canvas position and dimensions are presentation-only metadata stored locally under a version-specific key after drag/resize completion. No secret or resource configuration is written to local storage.

## Resource Catalog

The catalog loads from `GET /catalog/resources`. Search, category filtering, and drag-to-canvas are generic. Detailed catalog calls provide defaults, schema fields, parent/child constraints, dependency information, and networking/security/monitoring/backup guidance.

Container behavior and valid drop targets come from `valid_parent_types` and `valid_child_types`; React components contain no Azure hierarchy rules.

## Hierarchy and Relationships

Backend `parent_resource_id` maps to React Flow `parentId`. Child positions are converted to parent-relative coordinates. Moving a parent moves its visual descendants. Container size is expanded after child movement and cannot remain below child bounds.

Logical relationships and technical dependencies have separate edge treatments. Users enter relationship semantics explicitly; the backend creates the relationship and validation is rerun immediately.

## Resource Editing

Dropped resources are staged locally with catalog defaults and a generated semantic `resource_key`. The properties panel uses catalog JSON schema fields and separates identity, configuration, SKU, tags, guidance, and relationships. Backend persistence occurs only when the user applies changes.

Save states are explicit: Saved, Saving, Unsaved changes, and Save failed. Failed writes retain local form/canvas state.

## Version Integration

Architecture and version selectors load M8 records. Only DRAFT versions are editable. New versions are created through M8 snapshot cloning and selected after creation. Version comparison renders only the authoritative M8 response.

Before canonical writes, the client verifies that the selected version is still the latest draft. Conflicts preserve edits and offer Reload latest and Compare actions.

## Validation, Compliance, and Dependencies

M4 validation findings are grouped by backend severity/category. M5 technical control evaluations preserve PASS, FAIL, WARNING, RECOMMENDATION, and NOT_EVALUATED wording and explicitly avoid certification claims. Dependency findings are grouped as required, recommended, and optional; no resources are created automatically.

## Delete Safety

Deletion requires explicit confirmation and shows child impact. Containers with children must be reparented or emptied first. Related logical relationships and dependencies are removed explicitly before resource deletion, then the canonical snapshot is reloaded.

## Error Handling and Security

The centralized API client handles structured 400/401/403/404/409/422/500 responses and network failures without exposing stack traces. Immutable/stale/conflict responses preserve local state.

Secret-keyed catalog defaults and backend properties are stripped before retained UI state. Secret-bearing edits are rejected. No credentials, canonical configuration, or API errors are logged or stored in local storage.

## Backend Changes

Minimal integration only:

- CORS permits local Vite origins.
- Dependency analysis moved to a distinct `/dependency-analysis` route, removing a collision with dependency CRUD.
- Existing catalog networking, security, monitoring, and backup requirements are included in catalog detail responses.

No backend business logic, Terraform lifecycle, version semantics, or migrations were changed.

## Tests

Frontend tests cover architecture loading, selectors, catalog loading/search/drag data, node/container/hierarchy mapping, multiple roots, relationships, dependencies, selection properties, editing, save success/failure states, immutable versions, version creation/comparison, findings, deletion confirmation, API errors, stale conflicts, secret handling, layout persistence, and unknown catalog types.

Backend integration tests cover CORS, route separation, and catalog guidance serialization.

- Frontend test functions authored: 40
- Backend integration test functions authored: 3
- Collected: not runtime-collected
- Executed: no
- Passed: not claimed
- Failed: not claimed

## Performance

Catalog details load in parallel once and remain in memory. Search uses deferred input. Node components are memoized. Dragging and resizing remain local and persist only on completion. Architecture data is not refetched for every canvas movement.

## Runtime Verification

VS Code source diagnostics report no errors. Project-level configuration reports unresolved package type definitions because dependencies cannot be installed without Node/npm.

Frontend tests authored but not executed because the local environment does not have the required frontend runtime/test dependencies.

No Git/GitHub, Terraform, Azure, deployment, M10, or M11 operations were performed.

## Known Limitations

- Node/npm installation and browser verification remain required.
- Layout metadata is browser-local and does not synchronize across users/devices.
- Relationship type entry is free-form because the current catalog API does not publish allowed logical relationship types; backend validation remains authoritative.
- Resource deletion spans existing CRUD calls because the backend has no atomic impact/delete command. Failures are surfaced and canonical reload is available.
- Direct browser receipt of legacy secret-bearing canonical properties cannot be prevented by M9 without changing existing resource API contracts; M9 immediately strips them and never renders, logs, or persists them locally.

## M10 Readiness

M9 establishes the typed frontend, canonical mapping boundary, designer, catalog-driven forms, version controls, and analysis panels required before M10. M10 can begin after Node dependency installation and browser/test verification. M10 is not implemented here.
