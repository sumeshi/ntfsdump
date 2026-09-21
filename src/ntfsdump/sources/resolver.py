# coding: utf-8
from pathlib import Path
from typing import Optional, Union

import pytsk3

from ntfsdump.errors import NtfsDumpError
from ntfsdump.formats import VALID_IMAGE_FORMATS, get_format_handler
from ntfsdump.formats.detect import detect_image_format
from ntfsdump.vmware import VmwareVM
from ntfsdump.vmware import VirtualDiskInfo


class Source:
    """Base class for a resolved SOURCE that can produce a logical disk."""

    format: str = 'raw'
    path: Optional[Path] = None

    def get_img_info(self) -> pytsk3.Img_Info:
        raise NotImplementedError


class FileSource(Source):
    """A disk image file (RAW / E01 / VHD / VHDX / VMDK)."""

    def __init__(self, path: Path, image_format: str):
        self.path = Path(path)
        self.format = image_format

    def get_img_info(self) -> pytsk3.Img_Info:
        handler = get_format_handler(self.format)
        return handler.get_img_info(str(self.path))


class RawSource(FileSource):
    """A raw disk image."""

    format = 'raw'


class EwfSource(FileSource):
    """An EWF/E01 image (possibly split across multiple segments)."""

    format = 'e01'


class VhdSource(FileSource):
    """A VHD image (conectix)."""

    format = 'vhd'


class VhdxSource(FileSource):
    """A VHDX/AVHDX source, chain-aware for Hyper-V differencing disks.

    Mirrors :class:`VmdkSource`: the parent (checkpoint) chain is resolved
    from the VHDX metadata without merging or converting the image.
    """

    format = 'vhdx'


class VmdkSource(FileSource):
    """A VMDK source, chain-aware for split extents and snapshot chains."""

    format = 'vmdk'


_SOURCE_CLASSES = {
    'raw': RawSource,
    'e01': EwfSource,
    'vhd': VhdSource,
    'vhdx': VhdxSource,
    'vmdk': VmdkSource,
}


class VmwareSource(Source):
    """A VMware VM directory, VMX or VMSD resolved into a logical disk."""

    format = 'vmdk'

    def __init__(
        self,
        vm: VmwareVM,
        snapshot=None,
        disk: Optional[int] = None,
    ):
        self.vm = vm
        self.path = vm.directory
        self.snapshot = snapshot
        self.disk = disk

    @property
    def snapshots(self):
        return self.vm.snapshots

    @property
    def disks(self) -> list[VirtualDiskInfo]:
        if self.snapshot is not None:
            return self.vm.disks_for(self.snapshot)
        return self.vm.current_disks()

    def get_img_info(self) -> pytsk3.Img_Info:
        vmdk_path = self.vm.resolve_disk(self.snapshot, self.disk)
        handler = get_format_handler('vmdk')
        return handler.get_img_info(str(vmdk_path))


class SourceResolver:
    """Resolve a user supplied SOURCE into a concrete Source implementation."""

    NO_VM_FILES_MESSAGE = (
        "No VMware VM files (VMX, VMSD or VMDK) were found in directory: {}"
    )

    def resolve(
        self,
        source: Union[str, Path],
        image_format: Optional[str] = None,
        snapshot=None,
        disk: Optional[int] = None,
    ) -> Source:
        path = Path(source)

        if not path.exists():
            raise NtfsDumpError(f"No such file or directory: {source}")

        if path.is_dir():
            return self._resolve_vmware(path, snapshot=snapshot, disk=disk)

        suffix = path.suffix.lower()
        if suffix == '.vmsd':
            return self._resolve_vmware(
                path.parent,
                vmsd_path=path,
                snapshot=snapshot,
                disk=disk,
            )
        if suffix == '.vmx':
            return self._resolve_vmware(
                path.parent,
                vmx_path=path,
                snapshot=snapshot,
                disk=disk,
            )

        if snapshot is not None or disk is not None:
            raise NtfsDumpError(
                "--snapshot/--disk can only be used with a VMware SOURCE."
            )

        resolved_format = self._resolve_format(path, image_format)
        source_cls = _SOURCE_CLASSES.get(resolved_format)
        if source_cls is None:
            raise NtfsDumpError(f"Unknown image format: {resolved_format}")
        return source_cls(path, resolved_format)

    def _resolve_format(self, path: Path, image_format: Optional[str]) -> str:
        if image_format is not None:
            normalized = image_format.lower()
            if normalized not in VALID_IMAGE_FORMATS:
                raise NtfsDumpError(f"Unknown image format: {image_format}")
            return normalized
        return detect_image_format(path)

    def _resolve_vmware(
        self,
        directory: Path,
        vmx_path: Optional[Path] = None,
        vmsd_path: Optional[Path] = None,
        snapshot=None,
        disk: Optional[int] = None,
    ) -> VmwareSource:
        vm = VmwareVM(directory, vmx_path=vmx_path, vmsd_path=vmsd_path)
        if vm.vmx_path is None and vm.vmsd_path is None and not vm.disks:
            raise NtfsDumpError(
                self.NO_VM_FILES_MESSAGE.format(directory)
            )
        return VmwareSource(vm, snapshot=snapshot, disk=disk)
