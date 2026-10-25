"""Audit the exact installed runtime dependencies, without private package lookup."""
import importlib.metadata
from pathlib import Path
import subprocess
import sys
import tempfile
from packaging.requirements import Requirement

resolved = {}
pending = ['PyYAML', 'pypdf', 'fonttools']
while pending:
    name = pending.pop()
    normalized = name.lower().replace('_', '-')
    if normalized in resolved:
        continue
    distribution = importlib.metadata.distribution(name)
    resolved[normalized] = f'{distribution.metadata["Name"]}=={distribution.version}'
    for expression in distribution.requires or []:
        requirement = Requirement(expression)
        if requirement.marker is None or requirement.marker.evaluate({'extra': ''}):
            pending.append(requirement.name)

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'requirements.txt'
    path.write_text('\n'.join(sorted(resolved.values())) + '\n', encoding='utf-8')
    raise SystemExit(subprocess.call([sys.executable, '-m', 'pip_audit', '--strict', '--no-deps', '--disable-pip', '-r', str(path)]))
