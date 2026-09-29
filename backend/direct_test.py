#!/usr/bin/env python
"""Direct pytest execution."""
import sys
import os

os.chdir('d:\\azure-architect-companion\\backend')
sys.path.insert(0, '.')

# Import pytest
import pytest

# Run tests and capture results
exit_code = pytest.main([
    'tests/',
    '-v',
    '--tb=short',
    '-q',
    '--color=no',
    '--no-header'
])

print(f"\n\nTest run completed with exit code: {exit_code}")
if exit_code == 0:
    print("✓ All tests passed!")
else:
    print(f"✗ Tests failed with code {exit_code}")
