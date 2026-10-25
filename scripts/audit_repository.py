"""Small repository hygiene checks; not a legal or secret-detection guarantee."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from researchvault.documents import read_record, load_yaml

SKILLS = {'literature-discovery', 'literature-acquisition', 'systematic-literature-review',
          'zotero-fetcher', 'fulltext-archiver', 'paper-note-writer', 'knowledge-maintainer',
          'literature-retrieval', 'research-maintainer', 'experiment-manager', 'writing-support', 'ingest-orchestrator'}


def check_mit_license(root):
    path = Path(root) / 'LICENSE'
    if not path.resolve().is_relative_to(Path(root).resolve()):
        return ['MIT license file escapes the package root']
    try:
        text = path.read_text(encoding='utf-8-sig')
    except (OSError, UnicodeError):
        return ['Missing or unreadable MIT license file']
    # Full standard MIT text with the public project attribution; wrapping may vary.
    expected = '2c5699be917ee2f0acaf5415dae6f5dd7c9c838b3aac44dac13bdd7c39697a8a'
    actual = hashlib.sha256(' '.join(text.split()).encode('utf-8')).hexdigest()
    if actual != expected:
        return ['Missing or altered MIT license text or project copyright notice']
    return []


def audit():
    errors = []
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode('utf-8').split('\0')
    files = [ROOT / p for p in tracked if p]
    actual = {p.parent.name for p in (ROOT / 'skills').glob('*/SKILL.md')}
    if actual != SKILLS:
        errors.append('Canonical Skill inventory must equal the twelve specified roles')
    for name in sorted(actual):
        record = read_record(ROOT / 'skills' / name / 'SKILL.md', ROOT)
        if record.data.get('name') != name or not isinstance(record.data.get('description'), str) or not record.data['description'].strip():
            errors.append('Invalid Skill frontmatter: ' + name)
    forbidden = {'config/local.yaml', '.env', '.obsidian', '.zotero'}
    link_count = 0
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        if (relative in forbidden or any(part in {'runtime', 'cache', 'staging', 'personal-vault', '.obsidian', '.zotero', '.deps'} for part in path.relative_to(ROOT).parts)
                or path.suffix.lower() in {'.pdf', '.sqlite', '.db', '.cookies'} or path.name.startswith('.env.')):
            errors.append('Private/runtime artifact: ' + relative)
        try:
            text = path.read_text(encoding='utf-8-sig')
        except (UnicodeError, OSError):
            errors.append('Unexpected binary/unreadable tracked file: ' + relative)
            continue
        patterns = [r'gh[pousr]_[A-Za-z0-9]{30,}', r'sk-proj-[A-Za-z0-9_-]{30,}',
                    r'(?i)(?:api_key|saml_token|two_factor_secret|session_cookie)\s*[:=]\s*[\"\x27]?[A-Za-z0-9+/=_-]{24,}',
                    r'[A-Za-z]:[/\\](?:Users|Documents|CodexStorage)[/\\]', r'/(?:Users)/[^/\s]+/', r'/(?:home)/(?!synthetic/)[^/\s]+/']
        if any(re.search(pattern, text) for pattern in patterns):
            errors.append('Possible credential or machine-specific path: ' + relative)
        if path.suffix == '.md':
            for target in re.findall(r'\[[^\]\n]*\]\(([^)\n]+)\)', text):
                target = target.strip('<>').split('#', 1)[0]
                if not target or re.match(r'[a-zA-Z][a-zA-Z0-9+.-]*:', target):
                    continue
                target = unquote(target)
                resolved = (path.parent / target).resolve()
                link_count += 1
                if not resolved.is_relative_to(ROOT) or not resolved.exists():
                    errors.append('Missing/escaping local resource: ' + relative + ' -> ' + target)
        if relative.startswith('examples/synthetic-vault/') and path.suffix == '.md':
            if read_record(path, ROOT).data.get('synthetic') is not True:
                errors.append('Example record lacks explicit synthetic label: ' + relative)
    errors.extend(check_mit_license(ROOT))
    if '[MIT License](LICENSE)' not in (ROOT / 'LICENSE_STATUS.md').read_text(encoding='utf-8'):
        errors.append('Missing MIT license declaration')
    for path in (ROOT / 'templates').iterdir():
        if path.suffix == '.md':
            read_record(path, ROOT)
        elif path.suffix in {'.json', '.yaml'}:
            load_yaml(path.read_text(encoding='utf-8'))
    return {'valid': not errors, 'tracked_files': len(files), 'skills': len(actual), 'local_links': link_count,
            'errors': errors,
            'limits': 'Heuristic hygiene scan only; dependency vulnerabilities are audited separately.'}


if __name__ == '__main__':
    result = audit()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result['valid'] else 1)
