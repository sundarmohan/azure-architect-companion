#!/usr/bin/env python
"""Run backend tests and capture output."""
import subprocess
import sys

result = subprocess.run(
    [sys.executable, '-m', 'pytest', 'tests/', '-v', '--tb=short'],
    cwd='d:\\azure-architect-companion\\backend',
    capture_output=True,
    text=True
)

print("STDOUT:")
print(result.stdout)
print("\nSTDERR:")
print(result.stderr)
print(f"\nExit code: {result.returncode}")
