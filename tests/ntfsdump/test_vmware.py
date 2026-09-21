# coding: utf-8
from pathlib import Path

import pytest

from ntfsdump.errors import NtfsDumpError
from ntfsdump.vmware import MULTIPLE_DISKS_MESSAGE, VmwareVM, parse_vmx, parse_vmsd

FIXTURES = Path(__file__).parent / 'fixtures' / 'vmware'
WINDOWS_VM = FIXTURES / 'WindowsVM'
SINGLE_VM = FIXTURES / 'SingleVM'


def test_parse_vmx_detects_disks_and_skips_cdrom():
    disks = parse_vmx(WINDOWS_VM / 'WindowsVM.vmx')

    assert [(disk.id, disk.node) for disk in disks] == [
        (0, 'scsi0:0'),
        (1, 'scsi0:1'),
    ]
    assert [disk.path.name for disk in disks] == ['Windows.vmdk', 'Data.vmdk']
    assert all(disk.path.parent == WINDOWS_VM for disk in disks)


def test_parse_vmsd_snapshots_and_parents():
    snapshots = parse_vmsd(WINDOWS_VM / 'WindowsVM.vmsd')

    assert [snapshot.id for snapshot in snapshots] == ['1', '2', '3']
    assert [snapshot.name for snapshot in snapshots] == [
        'Before Windows Update',
        'After Windows Update',
        'Before Investigation',
    ]
    assert [snapshot.parent_id for snapshot in snapshots] == [None, '1', '2']
    assert all(snapshot.created_at is not None for snapshot in snapshots)
    assert snapshots[2].disks[1].filename == 'Data-000001.vmdk'


def test_current_disks_follow_snapshot_current():
    vm = VmwareVM(WINDOWS_VM)

    assert [(disk.id, disk.path.name) for disk in vm.current_disks()] == [
        (0, 'Windows-000003.vmdk'),
        (1, 'Data-000001.vmdk'),
    ]


def test_resolve_disk_for_snapshot_and_disk_id():
    vm = VmwareVM(WINDOWS_VM)

    assert vm.resolve_disk('3', 1).name == 'Data-000001.vmdk'
    assert vm.resolve_disk('3', 0).name == 'Windows-000003.vmdk'
    assert vm.resolve_disk('1', 0).name == 'Windows-000001.vmdk'


def test_resolve_disk_without_snapshot_requires_disk_id_when_multiple():
    vm = VmwareVM(WINDOWS_VM)

    with pytest.raises(NtfsDumpError, match=MULTIPLE_DISKS_MESSAGE.split('\n')[0]):
        vm.resolve_disk()


def test_single_disk_is_selected_automatically():
    vm = VmwareVM(SINGLE_VM)

    assert vm.resolve_disk().name == 'Single.vmdk'


def test_unknown_snapshot_id_raises():
    vm = VmwareVM(WINDOWS_VM)

    with pytest.raises(NtfsDumpError, match="Snapshot ID 42 was not found."):
        vm.disks_for('42')


def test_unknown_disk_id_raises():
    vm = VmwareVM(WINDOWS_VM)

    with pytest.raises(NtfsDumpError, match="Disk ID 9 was not found."):
        vm.resolve_disk('3', 9)


def test_vm_without_snapshot_metadata():
    vm = VmwareVM(SINGLE_VM)

    assert vm.snapshots == []
    assert vm.current_disks()[0].path.name == 'Single.vmdk'


def test_parse_vmsd_non_contiguous_indices(tmp_path):
    vmsd = tmp_path / 'gap.vmsd'
    vmsd.write_text('\n'.join([
        'snapshot.lastUID = "9"',
        'snapshot.numSnapshots = "2"',
        'snapshot.current = "9"',
        'snapshot1.uid = "4"',
        'snapshot1.displayName = "first"',
        'snapshot1.numDisks = "1"',
        'snapshot1.disk0.fileName = "a-000001.vmdk"',
        'snapshot1.disk0.node = "scsi0:0"',
        'snapshot2.uid = "9"',
        'snapshot2.parent = "4"',
        'snapshot2.displayName = "second"',
        'snapshot2.numDisks = "1"',
        'snapshot2.disk0.fileName = "a-000002.vmdk"',
        'snapshot2.disk0.node = "scsi0:0"',
        '',
    ]))

    snapshots = parse_vmsd(vmsd)

    assert [snapshot.id for snapshot in snapshots] == ['4', '9']
    assert snapshots[1].parent_id == '4'


def test_discover_vmdk_disks_in_directory_without_vmx(tmp_path):
    (tmp_path / 'disk-flat.vmdk').write_bytes(b'\x00' * 512)
    (tmp_path / 'disk.vmdk').write_text(
        '# Disk DescriptorFile\nversion=1\n'
    )

    vm = VmwareVM(tmp_path)

    assert vm.vmx_path is None
    assert [disk.path.name for disk in vm.disks] == ['disk.vmdk']


def test_snapshot_disks_without_node_get_unique_ids(tmp_path):
    vmsd = tmp_path / 'x.vmsd'
    vmsd.write_text('\n'.join([
        'snapshot.numSnapshots = "1"',
        'snapshot.current = "1"',
        'snapshot0.uid = "1"',
        'snapshot0.numDisks = "2"',
        'snapshot0.disk0.fileName = "a-000001.vmdk"',
        'snapshot0.disk0.node = "scsi0:0"',
        'snapshot0.disk1.fileName = "b-000001.vmdk"',
        '',
    ]))
    vmx = tmp_path / 'x.vmx'
    vmx.write_text('scsi0:0.present = "TRUE"\nscsi0:0.fileName = "a.vmdk"\n')

    vm = VmwareVM(tmp_path)
    ids = [disk.id for disk in vm.current_disks()]

    assert len(ids) == len(set(ids))
