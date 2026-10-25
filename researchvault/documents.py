"""One small boundary for human records and non-destructive file creation."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import yaml


class InvalidRecord(ValueError):
    pass


class DistinctKeys(yaml.SafeLoader):
    pass


def _object(loader, node):
    value = {}
    for left, right in node.value:
        key = loader.construct_object(left, deep=True)
        if not isinstance(key, str):
            raise InvalidRecord('Record mapping keys must be strings')
        if key in value:
            raise InvalidRecord(f'Repeated field: {key}')
        value[key] = loader.construct_object(right, deep=True)
    return value


DistinctKeys.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _object)


def load_yaml(text):
    try:
        return yaml.load(text, Loader=DistinctKeys)
    except yaml.YAMLError as exc:
        raise InvalidRecord('YAML cannot be read: ' + str(exc)) from exc


@dataclass
class Record:
    path: Path
    relative: str
    data: dict
    body: str

    @property
    def type(self):
        return self.data.get('type')


def read_record(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    if not path.is_relative_to(root):
        raise InvalidRecord('Record is outside the selected Vault')
    with path.open(encoding='utf-8-sig', newline='') as stream:
        text = stream.read()
    match = re.match(r'\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)', text, re.S)
    if match is None:
        raise InvalidRecord('Markdown record needs YAML frontmatter')
    data = load_yaml(match.group(1))
    if not isinstance(data, dict):
        raise InvalidRecord('Frontmatter must be an object')
    if 'type' in data and not isinstance(data['type'], str):
        raise InvalidRecord('Record type must be text')
    return Record(path, path.relative_to(root).as_posix(), data, text[match.end():])


def create_file(path, content):
    path = Path(path)
    payload = content.encode('utf-8') if isinstance(content, str) else content
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(payload)


def write_new(path, data, body):
    payload = '---\n' + yaml.safe_dump(data, sort_keys=False, allow_unicode=True) + '---\n' + body
    create_file(path, payload)


def diagnostic(code, path, detail, level='error'):
    return {'code': code, 'path': str(path), 'detail': str(detail), 'level': level}


def record_paths(settings):
    excluded = (settings.folder('templates'), settings.folder('metadata'))
    for path in sorted(settings.vault.rglob('*.md')):
        if '.git' in path.relative_to(settings.vault).parts or any(path.is_relative_to(p) for p in excluded):
            continue
        # Never follow a file symlink out of the chosen root.
        settings.resolve(path.relative_to(settings.vault).as_posix())
        yield path


def scan(settings):
    return [read_record(path, settings.vault) for path in record_paths(settings)]
