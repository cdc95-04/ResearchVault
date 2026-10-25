"""Explicit data roots; personal data never defaults into the source checkout."""
from __future__ import annotations

from dataclasses import dataclass
import copy
import os
import math
from pathlib import Path, PureWindowsPath

from .documents import load_yaml
from .safety import read_only_mode

REPOSITORY = Path(__file__).resolve().parent.parent
PATHS = {
    'inbox': '00-inbox', 'knowledge': '01-knowledge', 'papers': '02-papers',
    'fulltext': '03-fulltext', 'research': '04-research', 'projects': '05-projects',
    'experiments': '06-experiments', 'meetings': '07-meetings', 'writing': '08-writing',
    'courses': '09-courses', 'archive': '90-archive', 'templates': '99-templates', 'metadata': '.meta',
}
CHILDREN = {
    'knowledge': ['Concepts', 'Methods', 'Relations', 'Controversies', 'Benchmarks', 'Themes'],
    'research': ['Questions', 'Gaps', 'Hypotheses', 'Ideas', 'Research-Maps', 'Cards', 'Reviews'],
    'experiments': ['Contracts', 'Trials', 'Results', 'Active', 'Completed', 'Failed'],
    'writing': ['Claims'], 'projects': ['M1', 'M2', 'PhD'], 'papers': ['Other'],
    'inbox': ['Candidates'], 'metadata': ['claims', 'receipts', 'imports'],
}
DEFAULTS = {
    'schema_version': 2, 'vault_root': None,
    'synthetic': False, 'read_only': False, 'runtime_dir': None, 'paths': PATHS,
    'folders': CHILDREN, 'zotero': {'library_id': None, 'api_key_env': 'RESEARCHVAULT_ZOTERO_KEY'},
    'acquisition': {'enabled': False, 'max_bytes': 100 * 1024 * 1024, 'interval': 1.0},
    'discovery': {'enabled': True, 'limit': 10},
}


def relative(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('A nonempty relative path is required')
    value = value.replace('\\', '/')
    parts = value.split('/')
    if value.startswith('/') or PureWindowsPath(value).drive or any(p in ('', '.', '..') or ':' in p for p in parts):
        raise ValueError('Path must be relative and contain no traversal or drive')
    return value


def contained(root, value):
    root = Path(root).resolve()
    path = root.joinpath(*relative(value).split('/')).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Resolved path escapes its root')
    return path


def native(value, base):
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise ValueError('Explicit filesystem root is required')
    text = str(value)
    if text.replace('/', '\\').startswith(('\\\\?\\', '\\\\.\\')):
        raise ValueError('Windows device and extended namespace roots are unsupported')
    windows = PureWindowsPath(text)
    if windows.drive and (os.name != 'nt' or not windows.is_absolute()):
        raise ValueError('Foreign or drive-relative filesystem root')
    if os.name == 'nt' and text.startswith('/') and not text.startswith('//'):
        raise ValueError('POSIX root cannot be interpreted on Windows')
    path = Path(text).expanduser()
    return (path if path.is_absolute() else Path(base) / path).resolve()


def _overlaps(first, second):
    return first.is_relative_to(second) or second.is_relative_to(first)


def _outside_repository(path, repository, synthetic=False):
    if _overlaps(path, repository):
        allowed = [repository / 'examples', repository / 'tests' / 'fixtures', repository / 'synthetic-vault']
        if not synthetic or not any(path.is_relative_to(root) for root in allowed):
            raise ValueError('Real data roots must be outside the repository; only explicit synthetic fixtures may be inside')


def _merge(base, incoming):
    result = copy.deepcopy(base)
    for key, value in incoming.items():
        result[key] = _merge(result[key], value) if isinstance(result.get(key), dict) and isinstance(value, dict) else value
    return result


@dataclass
class Settings:
    vault: Path
    repository: Path
    runtime: Path | None
    options: dict

    @property
    def read_only(self):
        return read_only_mode(self.options.get('read_only', False))

    def folder(self, name):
        return contained(self.vault, self.options['paths'][name])

    def resolve(self, path):
        return contained(self.vault, path)

    def relative(self, path):
        target = Path(path).resolve()
        if not target.is_relative_to(self.vault):
            raise ValueError('Artifact is not inside the Vault')
        return target.relative_to(self.vault).as_posix()


def _configuration(config_path=None, cwd=None):
    working = Path(cwd or Path.cwd()).resolve()
    explicit = config_path or os.environ.get('RESEARCHVAULT_CONFIG')
    source = native(explicit, working) if explicit else working / 'config' / 'default.yaml'
    incoming = {}
    if source.exists():
        incoming = load_yaml(source.read_text(encoding='utf-8-sig'))
        if not isinstance(incoming, dict):
            raise ValueError('Configuration must be a mapping')
    elif explicit:
        raise ValueError('Requested configuration does not exist')
    if 'project_version' in incoming:
        raise ValueError('Remove project_version from configuration; package release comes from installed metadata')
    if 'language' in incoming:
        raise ValueError('Remove language from configuration; no runtime language setting is supported')
    if isinstance(incoming.get('zotero'), dict) and 'data_dir' in incoming['zotero']:
        raise ValueError('Remove zotero.data_dir from configuration; explicit environment inspection uses --zotero-data')
    options = _merge(DEFAULTS, incoming)
    read_only_mode(options.get('read_only'))
    return working, source, options


def configured_read_only(config_path=None, *, read_only=False, cwd=None):
    """Read the safety switch even for commands that need no Vault root."""
    read_only_mode(read_only)
    _, _, options = _configuration(config_path, cwd)
    return read_only or options['read_only']


def load_settings(config_path=None, vault=None, synthetic=False, cwd=None, *, read_only=False):
    read_only_mode(read_only)
    working, source, options = _configuration(config_path, cwd)
    options['read_only'] = read_only or options['read_only']
    if options.get('schema_version') != 2:
        raise ValueError('Supported Vault schema is 2')
    for group in ('paths', 'folders', 'zotero', 'acquisition', 'discovery'):
        if not isinstance(options.get(group), dict):
            raise ValueError(f'{group} must be a mapping')
    if set(options['paths']) != set(PATHS):
        raise ValueError('Configure the thirteen known path roles; custom categories belong in folders')
    if type(options.get('synthetic')) is not bool:
        raise ValueError('synthetic must be Boolean')
    is_synthetic = synthetic or options['synthetic']
    root_value = vault if vault is not None else options.get('vault_root')
    if root_value is None:
        raise ValueError('Choose --vault or vault_root in local config; no personal Vault is created by default')
    root = native(root_value, working if vault is not None else source.parent)
    _outside_repository(root, REPOSITORY, is_synthetic)
    resolved = [contained(root, value) for value in options['paths'].values()]
    for index, path in enumerate(resolved):
        if any(_overlaps(path, prior) for prior in resolved[:index]):
            raise ValueError('Configured path roles overlap')
    for role, values in options['folders'].items():
        if role not in PATHS or not isinstance(values, list):
            raise ValueError('Folder categories require a known role and a list')
        children = [contained(contained(root, options['paths'][role]), value) for value in values]
        if any(_overlaps(path, prior) for i, path in enumerate(children) for prior in children[:i]):
            raise ValueError('Folder categories overlap')
    library = options['zotero'].get('library_id')
    if library is not None and (type(library) is not int or library < 1):
        raise ValueError('library_id is null for the personal library or a positive group ID')
    env_name = options['zotero'].get('api_key_env')
    if not isinstance(env_name, str) or not env_name.replace('_', 'A').isalnum() or env_name[0].isdigit():
        raise ValueError('api_key_env must name an environment variable')
    if any(key.casefold() in {'api_key', 'token', 'password', 'cookies', 'secret'} for key in options['zotero']):
        raise ValueError('Store credential values in the environment, not configuration')
    for group in ('acquisition', 'discovery'):
        if type(options[group].get('enabled')) is not bool:
            raise ValueError(f'{group}.enabled must be Boolean')
    for group, field in (('acquisition', 'max_bytes'), ('discovery', 'limit')):
        if type(options[group].get(field)) is not int or options[group][field] < 1:
            raise ValueError(f'{group}.{field} must be a positive integer')
    interval = options['acquisition'].get('interval')
    if type(interval) not in (int, float) or not math.isfinite(interval) or interval < 0:
        raise ValueError('acquisition.interval must be a finite nonnegative number')
    runtime = None
    if options.get('runtime_dir') is not None:
        runtime = native(options['runtime_dir'], source.parent)
        _outside_repository(runtime, REPOSITORY, is_synthetic)
        if _overlaps(root, runtime):
            raise ValueError('Runtime must be separate from the Vault')
    options['synthetic'] = is_synthetic
    return Settings(root, REPOSITORY, runtime, options)
