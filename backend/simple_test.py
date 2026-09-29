#!/usr/bin/env python
"""Simple test runner."""
import subprocess
import os

os.chdir('d:\\azure-architect-companion\\backend')

# Run pytest
proc = subprocess.Popen(
    ['python', '-m', 'pytest', 'tests/', '-v', '--tb=short', '-q'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1
)

output_lines = []
for line in proc.stdout:
    output_lines.append(line)
    
proc.wait()

# Write output
with open('pytest_results.txt', 'w') as f:
    f.writelines(output_lines)
    f.write(f"\n\nReturn code: {proc.returncode}\n")

print(f"Wrote {len(output_lines)} lines to pytest_results.txt")
print(f"Return code: {proc.returncode}")
