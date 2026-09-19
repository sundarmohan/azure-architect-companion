# Azure Architect Companion - Backend

This is the backend implementation for Azure Architect Companion, focusing on Milestone 1: Canonical Architecture Model.

## Architecture

The backend implements the Canonical Architecture Model as the single source of truth for infrastructure architecture designs.

### Core Entities

1. **Architecture** - A complete infrastructure design
   - id, name, description, provider
   - Can have multiple versions

2. **ArchitectureVersion** - A version of an architecture
   - Tracks version_number, status, created_at, created_by
   - Contains resources, relationships, and dependencies

3. **Resource** - An Azure resource in the architecture
   - Supports hierarchy via parent_resource_id
   - Contains type, location, SKU, properties, tags
   - Examples: Resource Group, VNet, Subnet, VM, etc.

4. **Relationship** - Logical connection between resources
   - Distinct from hierarchy and dependencies
   - Example: VM connects to Load Balancer

5. **Dependency** - Technical provisioning dependency
   - resource_id depends_on depends_on_resource_id
   - Can be required or optional
   - Includes reason for the dependency

### Domain Distinction

Three distinct concepts are kept separate:

- **Hierarchy** (parent_resource_id): Resource containment
  - Resource Group → VNet → Subnet → Resource

- **Relationship**: Logical/topological connections
  - Resource A connects_to Resource B

- **Dependency**: Technical provisioning requirements
  - Resource A requires Resource B to be provisioned first

## Setup

### Prerequisites

- Python 3.14
- PostgreSQL (can be in Docker, but not required for Windows host)

### Installation

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create .env file (copy from .env.example):
```bash
cp .env.example .env
```

4. Update DATABASE_URL in .env if needed

## Running the Application

```bash
uvicorn app.main:app --reload
```

The API will be available at http://localhost:8000

Health check: http://localhost:8000/health

API documentation: http://localhost:8000/docs (Swagger UI)

## Database

### Migrations

Create a new migration:
```bash
alembic revision --autogenerate -m "Description"
```

Apply migrations:
```bash
alembic upgrade head
```

Revert migrations:
```bash
alembic downgrade -1
```

### Initial Setup

The initial migration (001_initial.py) creates all required tables:
- architectures
- architecture_versions
- resources
- relationships
- dependencies

## Testing

Run all tests:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=app
```

Run specific test file:
```bash
pytest tests/test_architecture.py
```

Run specific test:
```bash
pytest tests/test_architecture.py::TestArchitectureService::test_create_architecture
```

### Test Strategy

- Uses in-memory SQLite database for fast, isolated tests
- Each test function gets a fresh database instance
- Fixtures provide sample data for different resource types
- Tests cover:
  - Service layer business logic
  - API endpoints
  - Model relationships
  - Hierarchy support
  - Relationships and dependencies
  - Error handling and validation

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app factory
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py        # Settings and configuration
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py          # SQLAlchemy declarative base
│   │   └── session.py       # Database engine and session management
│   ├── models/
│   │   ├── __init__.py
│   │   └── models.py        # SQLAlchemy ORM models
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── schemas.py       # Pydantic API schemas
│   ├── services/
│   │   ├── __init__.py
│   │   └── services.py      # Business logic services
│   └── api/
│       ├── __init__.py
│       └── router.py        # API routes and endpoints
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Pytest configuration and fixtures
│   ├── test_architecture.py # Architecture and version tests
│   ├── test_resources.py    # Resource tests
│   ├── test_relationships_dependencies.py
│   └── test_api.py          # API endpoint tests
├── alembic/
│   ├── env.py               # Alembic environment config
│   ├── script.py.mako       # Migration template
│   └── versions/
│       └── 001_initial.py   # Initial migration
├── alembic.ini              # Alembic configuration
├── requirements.txt         # Python dependencies
├── pytest.ini               # Pytest configuration
├── .env.example             # Environment variables example
└── README.md                # This file
```

## Design Principles

- **Canonical Model is Source of Truth**: All decisions flow from the architecture model
- **UUID Identifiers**: All entities use UUID for global uniqueness
- **UTC Timestamps**: All timestamps are timezone-aware and in UTC
- **Strict Typing**: Python type hints throughout
- **Service Layer**: Business logic separated from HTTP handlers
- **Schema Separation**: Database models separate from API schemas
- **No Global Mutable State**: Dependency injection for all dependencies

## API Endpoints

### Architectures
- `POST /architectures` - Create
- `GET /architectures` - List
- `GET /architectures/{id}` - Get
- `PUT /architectures/{id}` - Update
- `DELETE /architectures/{id}` - Delete

### Versions
- `POST /architectures/{arch_id}/versions` - Create
- `GET /architectures/{arch_id}/versions` - List
- `GET /architectures/{arch_id}/versions/{id}` - Get

### Resources
- `POST /architectures/{arch_id}/versions/{version_id}/resources` - Create
- `GET /architectures/{arch_id}/versions/{version_id}/resources` - List
- `GET /architectures/{arch_id}/versions/{version_id}/resources/{id}` - Get

### Relationships
- `POST /architectures/{arch_id}/versions/{version_id}/relationships` - Create
- `GET /architectures/{arch_id}/versions/{version_id}/relationships` - List

### Dependencies
- `POST /architectures/{arch_id}/versions/{version_id}/dependencies` - Create
- `GET /architectures/{arch_id}/versions/{version_id}/dependencies` - List

## Future Milestones

This implementation is designed as a foundation for:
- Terraform generation
- Azure resource validation
- Compliance engine
- Deployment and conformance tracking
- UI/Frontend
- Authentication and authorization

The canonical model keeps all these concerns separate and maintains data integrity.
