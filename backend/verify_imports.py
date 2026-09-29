#!/usr/bin/env python
"""Verify models and schemas load correctly."""
import sys
import os

os.chdir('d:\\azure-architect-companion\\backend')
sys.path.insert(0, '.')

try:
    print("Attempting to import models...")
    from app.models import Relationship
    print("✓ Models imported successfully")
    
    print("\nChecking Relationship model:")
    print(f"  - Has 'relationship_metadata' attr: {hasattr(Relationship, 'relationship_metadata')}")
    print(f"  - Table columns: {list(Relationship.__table__.columns.keys())}")
    
    print("\nAttempting to import schemas...")
    from app.schemas import RelationshipResponse
    print("✓ Schemas imported successfully")
    
    print("\nRelationshipResponse schema:")
    print(f"  - model_config: {RelationshipResponse.model_config}")
    print(f"  - Fields: {RelationshipResponse.model_fields.keys()}")
    
    # Check the metadata field config
    metadata_field = RelationshipResponse.model_fields['metadata']
    print(f"  - metadata field: {metadata_field}")
    print(f"    - validation_alias: {metadata_field.validation_alias}")
    print(f"    - serialization_alias: {metadata_field.serialization_alias}")
    
    print("\n✓ All imports and checks passed!")
    
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
