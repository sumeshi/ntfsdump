# coding: utf-8
from dataclasses import dataclass, field
from os.path import abspath
from pathlib import Path, PureWindowsPath
from typing import BinaryIO, List, Optional

import pytsk3
import pyvmdk

from ntfsdump.errors import NtfsDumpError
from ntfsdump.formats.base import FormatHandler, BaseImgInfo
from ntfsdump.image_paths import confined_image_path


@dataclass
class VmdkChain:
    """A logical VMDK disk resolved from a descriptor and its parent chain."""

    handle: "pyvmdk.handle"
    handles: List["pyvmdk.handle"] = field(default_factory=list)
    extent_files: List[BinaryIO] = field(default_factory=list)
    source_paths: List[Path] = field(default_factory=list)


def _parent_candidates(child: Path, parent_filename: str, root: Path) -> List[Path]:
    """Map parent hints to local paths inside the initial disk directory."""
    normalized = parent_filename.replace("\\", "/")
    windows_path = PureWindowsPath(normalized)
    if windows_path.drive:
        candidates: List[Path] = []
        if len(windows_path.drive) == 2 and windows_path.root:
            stripped = normalized.split(":", 1)[1].lstrip("/")
            candidates.append(child.parent / stripped)
        candidates.append(child.parent / windows_path.name)
    elif normalized.startswith("/"):
        candidates = [child.parent / Path(normalized).name]
    else:
        candidates = [child.parent / normalized]

    unique: List[Path] = []
    for candidate in candidates:
        # Check lexical containment before any filesystem access.
        candidate = Path(abspath(candidate))
        if candidate.is_relative_to(root) and candidate not in unique:
            unique.append(candidate)
    return unique


def _resolve_parent(child: Path, parent_filename: str, root: Path) -> Path:
    """Pick a local parent without following symlinks or Windows junctions."""
    for candidate in _parent_candidates(child, parent_filename, root):
        try:
            candidate = confined_image_path(child.parent, str(candidate), root)
        except NtfsDumpError:
            continue
        if candidate.is_file():
            return candidate
    raise NtfsDumpError(f"Parent VMDK was not found: {parent_filename}")


def _safe_close(handle) -> None:
    try:
        handle.close()
    except Exception:
        pass


def open_vmdk_chain(
    path: Path,
    _seen: Optional[List[Path]] = None,
    _root: Optional[Path] = None,
) -> VmdkChain:
    """Open ``path`` and recursively attach its parent VMDK, without merging.

    Validated extent files are passed to libvmdk as file objects so that they
    are treated as a single logical disk. Snapshot/delta chains
    are linked through ``set_parent()`` so that unallocated blocks fall back to
    the parent image. Parents must stay within the initial disk directory;
    absolute and UNC hints are mapped to local candidates. No temporary RAW
    or merged VMDK is created.
    """
    path = Path(path)
    seen = list(_seen or [])
    resolved = path.resolve()
    root = _root if _root is not None else resolved.parent

    if resolved in seen:
        chain = " -> ".join(p.name for p in seen + [resolved])
        raise NtfsDumpError(f"Circular VMDK parent reference detected: {chain}")
    seen.append(resolved)

    handles: List["pyvmdk.handle"] = []
    extent_files: List[BinaryIO] = []
    source_paths = [resolved]
    try:
        handle = pyvmdk.handle()
        handles.append(handle)
        handle.open(str(path), mode="r")
        with resolved.open("rb") as descriptor_file:
            embedded_descriptor = descriptor_file.read(4) == b"KDMV"
        for extent in handle.extent_descriptors:
            if embedded_descriptor and handle.disk_type in (
                pyvmdk.disk_types.MONOLITHIC_SPARSE,
                pyvmdk.disk_types.STREAM_OPTIMIZED,
            ):
                # Embedded extents use the source itself even after it is renamed.
                extent_path = resolved
            else:
                extent_path = confined_image_path(
                    resolved.parent, extent.filename, root
                )
            extent_files.append(extent_path.open("rb"))
            source_paths.append(extent_path)
        handle.open_extent_data_files_as_file_objects(extent_files)

        parent_filename = handle.get_parent_filename()
        if parent_filename:
            parent = _resolve_parent(resolved, parent_filename, root)
            parent_chain = open_vmdk_chain(parent, seen, root)
            handles.extend(parent_chain.handles)
            extent_files.extend(parent_chain.extent_files)
            source_paths.extend(parent_chain.source_paths)
            try:
                handle.set_parent(parent_chain.handle)
            except Exception as exc:
                raise NtfsDumpError(
                    f"Unable to attach parent VMDK: {parent_filename} ({exc})"
                ) from exc
    except NtfsDumpError:
        for item in handles + extent_files:
            _safe_close(item)
        raise
    except Exception as exc:
        for item in handles + extent_files:
            _safe_close(item)
        raise NtfsDumpError(f"Unable to open VMDK: {path} ({exc})") from exc

    return VmdkChain(
        handle=handles[0],
        handles=handles,
        extent_files=extent_files,
        source_paths=source_paths,
    )


def probe_media_size(path: Path) -> Optional[int]:
    """Return the logical size of a VMDK descriptor, or None if unavailable."""
    try:
        handle = pyvmdk.handle()
        handle.open(str(path), mode="r")
        size = handle.get_media_size()
        handle.close()
        return int(size)
    except Exception:
        return None


class VMDKHandler(FormatHandler):
    def get_img_info(self, path: str) -> pytsk3.Img_Info:
        chain = open_vmdk_chain(Path(path))
        return BaseImgInfo(
            chain.handle,
            keepalive=chain.handles + chain.extent_files,
            source_paths=chain.source_paths,
        )
