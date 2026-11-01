from os.path import abspath
from pathlib import Path, PureWindowsPath
from typing import Iterable

from ntfsdump.errors import NtfsDumpError


def ensure_distinct_output(output: Path, source_paths: Iterable[Path]) -> None:
    """Reject an output that aliases an input image or one of its backing files."""
    output = Path(output)
    resolved_output = output.resolve()
    for source in source_paths:
        source = Path(source)
        same_file = resolved_output == source.resolve()
        if not same_file:
            try:
                same_file = output.samefile(source)
            except FileNotFoundError:
                pass
        if same_file:
            raise NtfsDumpError(f"Output would overwrite an input image file: {output}")


def confined_image_path(
    directory: Path, filename: str, root: Path | None = None
) -> Path:
    """Validate an image reference before probing or opening its target."""
    root = Path(abspath(root if root is not None else directory))
    normalized = filename.replace("\\", "/")
    hint = Path(normalized)
    if normalized.startswith("//") or (
        PureWindowsPath(normalized).drive and not hint.is_absolute()
    ):
        raise NtfsDumpError(f"External image reference is not allowed: {filename}")
    candidate = Path(abspath(directory / hint))
    if not candidate.is_relative_to(root):
        raise NtfsDumpError(f"Image reference escapes the image directory: {filename}")
    current = root
    for part in candidate.relative_to(root).parts:
        current = current / part
        if current.is_symlink() or current.is_junction():
            raise NtfsDumpError(
                f"Image reference uses a symlink or junction: {filename}"
            )
    return candidate
