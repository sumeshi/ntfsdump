# coding: utf-8
from pathlib import Path

import pyewf
import pyvhdi
import pyvmdk

from ntfsdump.errors import NtfsDumpError


def _is_vhdx(path: Path) -> bool:
    try:
        with path.open('rb') as f:
            return f.read(8) == b'vhdxfile'
    except OSError:
        return False


def _is_vmdk_descriptor(path: Path) -> bool:
    try:
        with path.open('rb') as f:
            head = f.read(64)
    except OSError:
        return False
    return head.startswith(b'# Disk DescriptorFile') or head.startswith(b'KDMV')


def detect_image_format(path) -> str:
    """Detect the image format of ``path`` by signature.

    Detection order follows the specification: EWF, VHD/VHDX, VMDK, then RAW
    as the fallback for files without a known signature.
    """
    p = Path(path)

    if not p.exists():
        raise NtfsDumpError(f"No such file or directory: {path}")
    if not p.is_file():
        raise NtfsDumpError("Unable to detect input image format.")

    try:
        if pyewf.check_file_signature(str(p)):
            return 'e01'
    except Exception:
        pass

    try:
        if pyvhdi.check_file_signature(str(p)):
            return 'vhdx' if _is_vhdx(p) else 'vhd'
    except Exception:
        pass

    try:
        if pyvmdk.check_file_signature(str(p)):
            return 'vmdk'
    except Exception:
        pass

    # VMDK descriptors are plain text and may not carry a binary signature.
    if _is_vmdk_descriptor(p):
        return 'vmdk'

    return 'raw'
