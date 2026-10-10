from os.path import abspath
from pathlib import Path, PureWindowsPath

from ntfsdump.errors import NtfsDumpError


def confined_image_path(directory: Path, filename: str, root: Path | None = None) -> Path:
    """Validate an image reference before probing or opening its target."""
    root = Path(abspath(root if root is not None else directory))
    normalized = filename.replace('\\', '/')
    hint = Path(normalized)
    if normalized.startswith('//') or (PureWindowsPath(normalized).drive and not hint.is_absolute()):
        raise NtfsDumpError(f"External image reference is not allowed: {filename}")
    candidate = Path(abspath(directory / hint))
    if not candidate.is_relative_to(root):
        raise NtfsDumpError(f"Image reference escapes the image directory: {filename}")
    current = root
    for part in candidate.relative_to(root).parts:
        current = current / part
        if current.is_symlink() or current.is_junction():
            raise NtfsDumpError(f"Image reference uses a symlink or junction: {filename}")
    return candidate
