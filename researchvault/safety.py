"""Small explicit read-only and validation-output boundaries."""
from pathlib import Path
import tempfile


def read_only_mode(value):
    if type(value) is not bool:
        raise ValueError('read_only must be Boolean')
    return value


def require_writable(settings, operation):
    if read_only_mode(getattr(settings, 'options', {}).get('read_only', False)):
        raise ValueError(f'{operation} is blocked in read-only validation mode')


def validation_output(workspace, relative_name, *, protected_roots=()):
    """Resolve an isolated output without creating it or accepting source roots.

    Callers must supply every selected real Vault and Zotero data root. Resolving
    both workspace and target rejects existing symlink/junction escapes.
    """
    from .config import REPOSITORY, contained, native, _overlaps

    if not isinstance(workspace, (str, Path)) or not str(workspace).strip():
        raise ValueError('Select an explicit validation workspace')
    root = native(workspace, Path.cwd())
    allowed = (REPOSITORY.resolve(), Path(tempfile.gettempdir()).resolve())
    if root in allowed or not any(root.is_relative_to(base) for base in allowed):
        raise ValueError('Validation workspace must be isolated below the repository or OS temporary directory')
    protected = [native(value, Path.cwd()) for value in protected_roots]
    if any(_overlaps(root, source) for source in protected):
        raise ValueError('Validation workspace overlaps a protected data root')
    target = contained(root, relative_name)
    if any(_overlaps(target, source) for source in protected):
        raise ValueError('Validation output overlaps a protected data root')
    return target
