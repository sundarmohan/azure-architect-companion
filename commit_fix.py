#!/usr/bin/env python
"""Direct git commit using subprocess."""
import subprocess
import os

os.chdir('d:\\azure-architect-companion')

# Stage files
files = [
    'backend/app/models/models.py',
    'backend/app/services/services.py', 
    'backend/app/schemas/schemas.py',
    'backend/tests/test_relationships_dependencies.py'
]

for f in files:
    result = subprocess.run(['git', 'add', f], capture_output=True, text=True)
    print(f"Added {f}: {result.returncode}")

# Commit
result = subprocess.run([
    'git', 'commit', '-m', 
    'Fix SQLAlchemy reserved metadata attribute in Relationship model'
], capture_output=True, text=True)

print("STDOUT:", result.stdout)
print("STDERR:", result.stderr)
print("Return code:", result.returncode)

# Check new commit
result = subprocess.run(['git', 'log', '--oneline', '-1'], capture_output=True, text=True)
print("Latest commit:", result.stdout)
