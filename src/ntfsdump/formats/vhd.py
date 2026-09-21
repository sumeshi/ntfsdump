# coding: utf-8
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import pytsk3
import pyvhdi

from ntfsdump.errors import NtfsDumpError
from ntfsdump.formats.base import FormatHandler, BaseImgInfo
from ntfsdump.formats.detect import is_vhdx_file

_WINDOWS_ABSOLUTE_RE = re.compile(r'^[A-Za-z]:[\\/]')


@dataclass
class VhdChain:
    """A logical VHD/VHDX disk resolved from its parent (differencing) chain."""

    handle: "pyvhdi.file"
    handles: List["pyvhdi.file"] = field(default_factory=list)


def _parent_path(child: Path, parent_filename: str) -> Path:
    """Resolve a parent filename relative to the child image.

    VHDX parent locators may contain absolute Windows paths (e.g.
    ``C:\\VMs\\Base\\disk.vhdx``). Those cannot be resolved on other
    platforms, so only the basename is used and looked up next to the child.
    """
    normalized = parent_filename.replace('\\', '/')

    if _WINDOWS_ABSOLUTE_RE.match(parent_filename) or normalized.startswith('//'):
        return child.parent / Path(normalized).name

    parent = Path(normalized)
    if parent.is_absolute():
        return parent
    return child.parent / parent


def _safe_close(handle) -> None:
    try:
        handle.close()
    except Exception:
        pass


def open_vhdx_chain(path: Path, _seen: Optional[List[Path]] = None) -> VhdChain:
    """Open ``path`` and recursively attach its parent, without merging.

    Hyper-V checkpoints are differencing VHDX/AVHDX files that reference their
    parent from the VHDX metadata (parent locator). The chain is linked with
    ``set_parent()`` so that unallocated blocks fall back to the parent image.
    No merge, conversion or checkpoint operation is performed.
    """
    path = Path(path)
    seen = list(_seen or [])
    resolved = path.resolve()

    is_vhdx = is_vhdx_file(path)
    family = 'VHDX' if is_vhdx else 'VHD'
    parent_label = 'AVHDX' if is_vhdx else 'VHD'

    if resolved in seen:
        chain = ' -> '.join(p.name for p in seen + [resolved])
        raise NtfsDumpError(
            f"Circular {family} parent reference detected: {chain}"
        )
    seen.append(resolved)

    handles: List["pyvhdi.file"] = []
    try:
        handle = pyvhdi.file()
        handles.append(handle)
        handle.open(str(path), mode='r')

        parent_filename = handle.get_parent_filename()
        if parent_filename:
            parent = _parent_path(path, parent_filename)
            if not parent.exists():
                raise NtfsDumpError(
                    f"Parent {parent_label} was not found: {parent_filename}"
                )
            parent_chain = open_vhdx_chain(parent, seen)
            handles.extend(parent_chain.handles)
            try:
                handle.set_parent(parent_chain.handle)
            except Exception as exc:
                raise NtfsDumpError(
                    f"Unable to attach parent {parent_label}: "
                    f"{parent_filename} ({exc})"
                ) from exc
    except NtfsDumpError:
        for item in handles:
            _safe_close(item)
        raise
    except Exception as exc:
        for item in handles:
            _safe_close(item)
        raise NtfsDumpError(f"Unable to open {family} image: {path} ({exc})") from exc

    return VhdChain(handle=handles[0], handles=handles)


class VHDHandler(FormatHandler):
    def get_img_info(self, path: str) -> pytsk3.Img_Info:
        chain = open_vhdx_chain(Path(path))
        return BaseImgInfo(chain.handle, keepalive=chain.handles)
