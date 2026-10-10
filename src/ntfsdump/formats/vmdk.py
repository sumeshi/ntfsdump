# coding: utf-8
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import re

import pytsk3
import pyvmdk

from ntfsdump.errors import NtfsDumpError
from ntfsdump.formats.base import FormatHandler, BaseImgInfo


@dataclass
class VmdkChain:
    """A logical VMDK disk resolved from a descriptor and its parent chain."""

    handle: "pyvmdk.handle"
    handles: List["pyvmdk.handle"] = field(default_factory=list)


_WINDOWS_ABSOLUTE_RE = re.compile(r'^[A-Za-z]:[\\/]')


def _parent_candidates(child: Path, parent_filename: str) -> List[Path]:
    """Candidate paths for a parent disk referenced by ``parent_filename``.

    A Windows absolute path from the original host is tried verbatim first
    (valid when ntfsdump runs on Windows or the original layout is restored;
    it is only used when it is actually absolute on this platform so that a
    POSIX run never resolves it relative to the current working directory),
    then the drive-stripped path relative to the child directory, then the
    basename fallback.
    """
    normalized = parent_filename.replace('\\', '/')

    if _WINDOWS_ABSOLUTE_RE.match(parent_filename):
        candidates: List[Path] = []
        verbatim = Path(parent_filename)
        if verbatim.is_absolute():
            candidates.append(verbatim)
        stripped = normalized.split(':', 1)[1].lstrip('/')
        candidates.append(child.parent / stripped)
        candidates.append(child.parent / Path(normalized).name)
    else:
        parent = Path(normalized)
        if parent.is_absolute():
            candidates = [parent]
        else:
            candidates = [child.parent / parent]

    unique: List[Path] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def _resolve_parent(child: Path, parent_filename: str) -> Path:
    """Pick the first existing candidate parent path."""
    for candidate in _parent_candidates(child, parent_filename):
        if candidate.exists():
            return candidate
    raise NtfsDumpError(f"Parent VMDK was not found: {parent_filename}")


def _safe_close(handle) -> None:
    try:
        handle.close()
    except Exception:
        pass


def open_vmdk_chain(path: Path, _seen: Optional[List[Path]] = None) -> VmdkChain:
    """Open ``path`` and recursively attach its parent VMDK, without merging.

    Split extents are opened through ``open_extent_data_files()`` so that the
    extent files are treated as a single logical disk. Snapshot/delta chains
    are linked through ``set_parent()`` so that unallocated blocks fall back to
    the parent image. No temporary RAW or merged VMDK is created.
    """
    path = Path(path)
    seen = list(_seen or [])
    resolved = path.resolve()

    if resolved in seen:
        chain = ' -> '.join(p.name for p in seen + [resolved])
        raise NtfsDumpError(f"Circular VMDK parent reference detected: {chain}")
    seen.append(resolved)

    handles: List["pyvmdk.handle"] = []
    try:
        handle = pyvmdk.handle()
        handles.append(handle)
        handle.open(str(path), mode='r')
        handle.open_extent_data_files()

        parent_filename = handle.get_parent_filename()
        if parent_filename:
            parent = _resolve_parent(path, parent_filename)
            parent_chain = open_vmdk_chain(parent, seen)
            handles.extend(parent_chain.handles)
            try:
                handle.set_parent(parent_chain.handle)
            except Exception as exc:
                raise NtfsDumpError(
                    f"Unable to attach parent VMDK: {parent_filename} ({exc})"
                ) from exc
    except NtfsDumpError:
        for item in handles:
            _safe_close(item)
        raise
    except Exception as exc:
        for item in handles:
            _safe_close(item)
        raise NtfsDumpError(f"Unable to open VMDK: {path} ({exc})") from exc

    return VmdkChain(handle=handles[0], handles=handles)


def probe_media_size(path: Path) -> Optional[int]:
    """Return the logical size of a VMDK descriptor, or None if unavailable."""
    try:
        handle = pyvmdk.handle()
        handle.open(str(path), mode='r')
        size = handle.get_media_size()
        handle.close()
        return int(size)
    except Exception:
        return None


class VMDKHandler(FormatHandler):
    def get_img_info(self, path: str) -> pytsk3.Img_Info:
        chain = open_vmdk_chain(Path(path))
        return BaseImgInfo(chain.handle, keepalive=chain.handles)
