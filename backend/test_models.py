#!/usr/bin/env python
"""Quick test to verify SQLAlchemy models load without reserved name errors."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app.models import Architecture, ArchitectureVersion, Resource, Relationship, Dependency
    from app.schemas import RelationshipResponse
    print("✓ Models imported successfully")
    print("✓ Relationship model has 'relationship_metadata' attribute:", hasattr(Relationship, 'relationship_metadata'))
    print("✓ Relationship.__table__.columns:", list(Relationship.__table__.columns.keys()))
    print("✓ All models loaded without SQLAlchemy reserved name errors")
    sys.exit(0)
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
