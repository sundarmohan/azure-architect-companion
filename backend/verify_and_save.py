#!/usr/bin/env python
"""Verify imports and write results to file."""
import sys
import os
import io
from contextlib import redirect_stdout, redirect_stderr

os.chdir('d:\\azure-architect-companion\\backend')
sys.path.insert(0, '.')

output = io.StringIO()
errors = io.StringIO()

try:
    with redirect_stdout(output), redirect_stderr(errors):
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
        print(f"  - Fields: {list(RelationshipResponse.model_fields.keys())}")
        
        # Check the metadata field config
        metadata_field = RelationshipResponse.model_fields['metadata']
        print(f"  - metadata field validation_alias: {metadata_field.validation_alias}")
        print(f"  - metadata field serialization_alias: {metadata_field.serialization_alias}")
        
        print("\n✓ All imports and checks passed!")
        status = "SUCCESS"
        
except Exception as e:
    print(f"\n✗ Error: {e}", file=errors)
    import traceback
    traceback.print_exc(file=errors)
    status = "FAILED"

# Write to file
with open('verify_results.txt', 'w') as f:
    f.write("=== VERIFICATION RESULTS ===\n\n")
    f.write("STDOUT:\n")
    f.write(output.getvalue())
    f.write("\n\nSTDERR:\n")
    f.write(errors.getvalue())
    f.write(f"\n\nStatus: {status}\n")

print("Results written to verify_results.txt", file=sys.stderr)
