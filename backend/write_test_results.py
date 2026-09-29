#!/usr/bin/env python
"""Run backend tests and write output to file."""
import subprocess
import sys
import os

os.chdir('d:\\azure-architect-companion\\backend')

result = subprocess.run(
    [sys.executable, '-m', 'pytest', 'tests/', '-v', '--tb=short'],
    capture_output=True,
    text=True,
    timeout=120
)

# Write to file
with open('test_output.txt', 'w') as f:
    f.write("=== PYTEST RESULTS ===\n\n")
    f.write("STDOUT:\n")
    f.write(result.stdout)
    f.write("\n\nSTDERR:\n")
    f.write(result.stderr)
    f.write(f"\n\nExit code: {result.returncode}\n")

print("Test output written to test_output.txt")
print("Exit code:", result.returncode)
