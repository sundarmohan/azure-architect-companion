# Azure Architect Companion — Copilot Instructions

## Product

Azure Architect Companion is an Azure infrastructure architecture platform.

The user visually designs Azure infrastructure, validates the architecture,
generates modular Terraform, plans and deploys the infrastructure, and
compares the desired architecture with actual Azure resources.

Core lifecycle:

DESIGN
→ DEPENDENCY VALIDATION
→ COMPLIANCE VALIDATION
→ AZURE LIVE VALIDATION
→ TERRAFORM GENERATION
→ FMT / VALIDATE
→ PLAN
→ APPLY
→ AZURE
→ POST-DEPLOYMENT CONFORMANCE

Architecture changes create new architecture versions.

---

## Core Principle

The Canonical Architecture Model is the single source of truth.

Do NOT make Terraform files the source of truth.

Flow:

Visual Designer
→ Canonical Architecture Model
→ Validation
→ Terraform Generator
→ Terraform Files
→ Terraform Plan
→ Terraform Apply
→ Actual Azure
→ Conformance

---

## Architect Control

The user is the architect.

AI may:

- explain
- recommend
- identify missing dependencies
- identify risks
- propose remediation
- analyze changes
- explain Terraform plans
- analyze deployment failures

AI must NOT silently redesign the user's architecture.

AI recommendations must be explicit and reviewable.

---

## Terraform

Terraform generation must be deterministic.

Support:

- terraform init
- terraform fmt
- terraform validate
- terraform plan
- terraform apply -auto-approve
- terraform output
- terraform refresh
- terraform plan -destroy
- terraform destroy

Terraform execution must be non-interactive.

Never require interactive Terraform variable input.

Use modular Terraform files organized by infrastructure domain.

Terraform automatically evaluates all `.tf` files in a module as one dependency graph.

Prefer implicit Terraform references over unnecessary `depends_on`.

---

## Secrets

Never store real secrets in:

- terraform.tfvars
- source code
- Git
- architecture JSON
- logs

Use Azure Key Vault or secure runtime injection.

Infrastructure provisioning and secret/configuration provisioning may be separate phases.

---

## Azure

Never fake Azure responses.

Azure-dependent functionality must use an explicit adapter/service boundary.

If Azure connectivity is unavailable, return a clear state such as:

AZURE_ADAPTER_NOT_CONFIGURED

Do not invent:

- SKUs
- regions
- quotas
- resource capabilities
- Azure resource IDs
- deployment results

---

## Resource Catalog

The Resource Catalog is the authoritative application knowledge layer for
supported Azure resources.

Catalog entries should contain, where applicable:

- Azure resource type
- Terraform resource mapping
- required properties
- defaults
- required dependencies
- recommended dependencies
- optional dependencies
- parent/child relationships
- networking requirements
- security requirements
- monitoring requirements
- backup requirements
- compliance rules

Do not hardcode the Azure catalog inside React components.

---

## Dependency Engine

Distinguish:

1. Visual/logical relationships
2. Technical infrastructure dependencies

Example:

VM

Required:
- Resource Group
- NIC
- OS disk

Recommended:
- NSG
- Monitoring
- Backup

A dependency should not be silently introduced into the user's architecture.

Required dependencies may be proposed or automatically created using safe
defaults where explicitly permitted by the product design.

---

## Compliance

Compliance is separate from Terraform generation.

Validation results use:

- BLOCK
- REQUIRED / POLICY-DEPENDENT
- RECOMMENDATION

Do not claim that technical validation alone provides legal or regulatory
compliance.

AI may explain findings and propose remediation.

Deterministic policy rules control enforcement.

---

## Versioning

Every architecture is versioned.

Example:

Architecture V1
Architecture V2
Architecture V3

Track:

- architecture version
- resource changes
- property changes
- dependency changes
- Terraform generated version
- changed Terraform files
- deployment
- Terraform plan
- Terraform state
- Azure snapshot
- conformance result

Unrelated Terraform files should not be rewritten unnecessarily.

---

## Conformance

After deployment compare:

Desired Architecture
vs
Terraform State
vs
Actual Azure

Do not compare raw Azure JSON directly against Terraform files.

Normalize Azure resources into the canonical infrastructure model first.

Report exact differences.

Example:

Expected:
public_network_access = false

Actual:
public_network_access = true

---

## Backend

Preferred backend:

Python + FastAPI

Use:

- strict typing
- Pydantic models
- SQLAlchemy
- PostgreSQL
- clear service boundaries
- unit tests
- integration tests

Business logic must remain outside API route handlers.

---

## Frontend

Preferred frontend:

React + TypeScript

Architecture designer should use React Flow or an equivalent graph-based
designer.

Do not put infrastructure business logic into React components.

Frontend communicates with backend APIs.

---

## Database

PostgreSQL is the primary application database.

Persist at minimum:

- architectures
- architecture versions
- resources
- relationships
- dependencies
- validation results
- Terraform versions
- Terraform file changes
- deployments
- audit events
- conformance results

---

## Security

Follow secure-by-default development.

Never commit:

- passwords
- API keys
- access tokens
- certificates
- private keys
- Azure credentials
- production secrets

---

## Development Rules

Before implementing a major feature:

1. Understand the canonical model.
2. Check existing interfaces.
3. Keep boundaries between services.
4. Add tests.
5. Avoid unnecessary dependencies.
6. Do not rewrite unrelated code.
7. Keep changes small and reviewable.

Do not build the entire product in one change.

Implement one milestone at a time.

---

## First Development Milestone

The first coding milestone is:

CANONICAL ARCHITECTURE MODEL

Implement:

- architecture model
- resource model
- relationship model
- dependency model
- properties
- hierarchy
- version identifier
- PostgreSQL persistence
- Pydantic schemas
- SQLAlchemy models
- unit tests

Do NOT implement the UI, Terraform generator, Azure deployment,
compliance engine, or AI agents in this first milestone.
