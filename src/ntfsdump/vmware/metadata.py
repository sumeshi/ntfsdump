# coding: utf-8
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from ntfsdump.errors import NtfsDumpError


MULTIPLE_DISKS_MESSAGE = (
    "Multiple virtual disks were found.\n"
    "Use --list-disks and --disk to select a disk."
)
NO_SNAPSHOT_METADATA_MESSAGE = "No VMware snapshot metadata was found."
NO_DISKS_MESSAGE = "No VMware virtual disks were found."


@dataclass
class VirtualDiskInfo:
    id: int
    node: str
    path: Path
    size: Optional[int] = None


@dataclass
class SnapshotDiskInfo:
    index: int
    node: Optional[str]
    filename: str

    def path(self, directory: Path) -> Path:
        if Path(self.filename).is_absolute():
            return Path(self.filename)
        return directory / self.filename


@dataclass
class SnapshotInfo:
    id: str
    name: str = ''
    description: str = ''
    created_at: Optional[datetime] = None
    parent_id: Optional[str] = None
    disks: List[SnapshotDiskInfo] = field(default_factory=list)

    def disk_for_node(self, node: Optional[str]) -> Optional[SnapshotDiskInfo]:
        if node is None:
            return None
        for disk in self.disks:
            if disk.node == node:
                return disk
        return None


_VMX_DISK_RE = re.compile(
    r'^(?P<ctrl>[A-Za-z]+)(?P<ctrlno>\d+):(?P<unit>\d+)\.(?P<key>\w+)$'
)
_CONTROLLER_PRIORITY = {'scsi': 0, 'sata': 1, 'nvme': 2, 'ide': 3}


def _parse_key_values(path: Path) -> Dict[str, str]:
    """Parse a VMware VMX/VMSD style ``key = "value"`` file."""
    result: Dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return result

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = value[1:-1]
        result[key] = value
    return result


def _parse_creation_time(high: Optional[str], low: Optional[str]) -> Optional[datetime]:
    if high is None and low is None:
        return None
    try:
        high_value = int(high) if high else 0
        low_value = int(low) if low else 0
        if low_value < 0:
            low_value += 1 << 32
        if high_value < 0:
            high_value += 1 << 32
        microseconds = (high_value << 32) | (low_value & 0xFFFFFFFF)
        if microseconds <= 0:
            return None
        return datetime.fromtimestamp(microseconds / 1_000_000, tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def _disk_sort_key(node: str) -> tuple:
    match = re.match(r'^(?P<ctrl>[A-Za-z]+)(?P<ctrlno>\d+):(?P<unit>\d+)$', node)
    if not match:
        return (99, 99, 99, node)
    ctrl = match.group('ctrl').lower()
    return (
        _CONTROLLER_PRIORITY.get(ctrl, 50),
        int(match.group('ctrlno')),
        int(match.group('unit')),
    )


_VMDK_EXTENT_OR_DELTA_RE = re.compile(
    r'-(?:s|f)\d+\.vmdk$|-\d{6}\.vmdk$|-flat\.vmdk$', re.IGNORECASE
)


def _looks_like_vmdk_descriptor(path: Path) -> bool:
    try:
        with path.open('rb') as f:
            head = f.read(64)
    except OSError:
        return False
    return head.startswith(b'# Disk DescriptorFile') or head.startswith(b'KDMV')


def discover_vmdk_disks(directory: Path) -> List[VirtualDiskInfo]:
    """Fallback disk discovery for a directory without VMX/VMSD.

    Split extent and snapshot delta files are ignored so that only the base
    descriptor is treated as a disk.
    """
    directory = Path(directory)
    if not directory.is_dir():
        return []

    candidates = [
        entry
        for entry in sorted(directory.iterdir())
        if entry.is_file()
        and entry.suffix.lower() == '.vmdk'
        and not _VMDK_EXTENT_OR_DELTA_RE.search(entry.name)
        and _looks_like_vmdk_descriptor(entry)
    ]
    return [
        VirtualDiskInfo(id=index, node=f"disk{index}", path=entry)
        for index, entry in enumerate(candidates)
    ]


def parse_vmx(path: Path) -> List[VirtualDiskInfo]:
    """Parse the virtual disk layout from a VMX file."""
    path = Path(path)
    directory = path.parent
    values = _parse_key_values(path)

    devices: Dict[str, Dict[str, str]] = {}
    for key, value in values.items():
        match = _VMX_DISK_RE.match(key)
        if not match:
            continue
        node = f"{match.group('ctrl')}{match.group('ctrlno')}:{match.group('unit')}"
        devices.setdefault(node, {})[match.group('key').lower()] = value

    disks: List[VirtualDiskInfo] = []
    for node in sorted(devices, key=_disk_sort_key):
        device = devices[node]
        if device.get('present', 'TRUE').lower() == 'false':
            continue
        filename = device.get('filename')
        if not filename:
            continue
        device_type = device.get('devicetype', '').lower()
        if 'cdrom' in device_type:
            continue
        disk_path = Path(filename)
        if not disk_path.is_absolute():
            disk_path = directory / filename
        disks.append(VirtualDiskInfo(id=0, node=node, path=disk_path))

    for index, disk in enumerate(disks):
        disk.id = index
    return disks


_VMSD_SNAPSHOT_RE = re.compile(r'^snapshot(\d+)\.')


def parse_vmsd(path: Path) -> List[SnapshotInfo]:
    """Parse snapshot metadata from a VMSD file.

    VMware does not renumber ``snapshotN`` entries when a snapshot is deleted,
    so indices may be non-contiguous (e.g. ``snapshot1`` and ``snapshot3``).
    They are discovered from the keys rather than assumed to be ``0..N-1``.
    """
    values = _parse_key_values(Path(path))

    indices = {
        int(match.group(1))
        for key in values
        if (match := _VMSD_SNAPSHOT_RE.match(key))
    }
    if not indices:
        try:
            count = int(values.get('snapshot.numSnapshots', '0'))
        except ValueError:
            count = 0
        indices = set(range(count))

    snapshots: List[SnapshotInfo] = []
    for index in sorted(indices):
        prefix = f'snapshot{index}.'
        uid = values.get(prefix + 'uid')
        if uid is None:
            continue

        parent = values.get(prefix + 'parent')
        if parent in (None, '', '0', uid):
            parent = None

        try:
            num_disks = int(values.get(prefix + 'numDisks', '0'))
        except ValueError:
            num_disks = 0

        disks: List[SnapshotDiskInfo] = []
        for disk_index in range(num_disks):
            disk_prefix = f'{prefix}disk{disk_index}.'
            filename = values.get(disk_prefix + 'fileName')
            node = values.get(disk_prefix + 'node')
            if not filename:
                continue
            disks.append(
                SnapshotDiskInfo(index=disk_index, node=node, filename=filename)
            )

        snapshots.append(
            SnapshotInfo(
                id=uid,
                name=values.get(prefix + 'displayName', ''),
                description=values.get(prefix + 'description', ''),
                created_at=_parse_creation_time(
                    values.get(prefix + 'createTimeHigh'),
                    values.get(prefix + 'createTimeLow'),
                ),
                parent_id=parent,
                disks=disks,
            )
        )
    return snapshots


class VmwareVM:
    """Resolve disks and snapshots for a VMware VM directory."""

    def __init__(
        self,
        directory: Path,
        vmx_path: Optional[Path] = None,
        vmsd_path: Optional[Path] = None,
    ):
        self.directory = Path(directory)
        self.vmx_path = Path(vmx_path) if vmx_path else self._find('.vmx')
        self.vmsd_path = Path(vmsd_path) if vmsd_path else self._find('.vmsd')

        self.disks: List[VirtualDiskInfo] = (
            parse_vmx(self.vmx_path) if self.vmx_path else []
        )
        if not self.disks:
            self.disks = discover_vmdk_disks(self.directory)
        self.snapshots: List[SnapshotInfo] = (
            parse_vmsd(self.vmsd_path) if self.vmsd_path else []
        )
        self.current_uid = self._parse_current_uid()

    def _find(self, suffix: str) -> Optional[Path]:
        if not self.directory.is_dir():
            return None
        for entry in sorted(self.directory.iterdir()):
            if entry.is_file() and entry.suffix.lower() == suffix:
                return entry
        return None

    def _parse_current_uid(self) -> Optional[str]:
        if not self.vmsd_path:
            return None
        values = _parse_key_values(self.vmsd_path)
        return values.get('snapshot.current')

    def get_snapshot(self, snapshot_id) -> Optional[SnapshotInfo]:
        for snapshot in self.snapshots:
            if str(snapshot.id) == str(snapshot_id):
                return snapshot
        return None

    def _snapshot_disks(self, snapshot: SnapshotInfo) -> List[VirtualDiskInfo]:
        if not snapshot.disks:
            return list(self.disks)

        node_to_id = {disk.node: disk.id for disk in self.disks}
        used_ids = set()
        disks: List[VirtualDiskInfo] = []
        for position, snapshot_disk in enumerate(snapshot.disks):
            disk_id = node_to_id.get(snapshot_disk.node)
            if disk_id is None or disk_id in used_ids:
                disk_id = position
                while disk_id in used_ids:
                    disk_id += 1
            used_ids.add(disk_id)
            disks.append(
                VirtualDiskInfo(
                    id=disk_id,
                    node=snapshot_disk.node or f"disk{position}",
                    path=snapshot_disk.path(self.directory),
                )
            )
        return sorted(disks, key=lambda disk: disk.id)

    def current_disks(self) -> List[VirtualDiskInfo]:
        if self.current_uid:
            snapshot = self.get_snapshot(self.current_uid)
            if snapshot is not None:
                return self._snapshot_disks(snapshot)
        return list(self.disks)

    def disks_for(self, snapshot_id) -> List[VirtualDiskInfo]:
        snapshot = self.get_snapshot(snapshot_id)
        if snapshot is None:
            raise NtfsDumpError(f"Snapshot ID {snapshot_id} was not found.")
        return self._snapshot_disks(snapshot)

    def resolve_disk(self, snapshot=None, disk=None) -> Path:
        """Return the VMDK descriptor path for the requested snapshot/disk."""
        if snapshot is not None:
            disks = self.disks_for(snapshot)
        else:
            disks = self.current_disks()

        if not disks:
            raise NtfsDumpError(NO_DISKS_MESSAGE)

        if disk is None:
            if len(disks) == 1:
                selected = disks[0]
            else:
                raise NtfsDumpError(MULTIPLE_DISKS_MESSAGE)
        else:
            matches = [candidate for candidate in disks if candidate.id == disk]
            if not matches:
                raise NtfsDumpError(f"Disk ID {disk} was not found.")
            selected = matches[0]

        return selected.path
