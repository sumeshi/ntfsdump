# coding: utf-8
from pathlib import Path

import pytest

from ntfsdump.errors import NtfsDumpError
from ntfsdump.image import is_ntfs_volume_description
from ntfsdump.sources import FileSource, SourceResolver, VmwareSource

SECTOR = 512
FIXTURES = Path(__file__).parent / 'fixtures' / 'vmware'


def test_ntfs_volume_descriptions():
    # MBR: TSK reports NTFS partitions as "NTFS / exFAT (0x07)".
    assert is_ntfs_volume_description('NTFS / exFAT (0x07)')
    # GPT: TSK labels partitions from their type GUID, not the filesystem.
    assert is_ntfs_volume_description('Basic data partition')
    assert is_ntfs_volume_description('Windows Recovery Environment')
    # Non-NTFS candidates.
    assert not is_ntfs_volume_description('EFI system partition')
    assert not is_ntfs_volume_description('Linux filesystem data')
    assert not is_ntfs_volume_description('Unallocated')
    assert not is_ntfs_volume_description('Microsoft Reserved Partition')


def _write_vmdk(directory: Path, name: str, sectors: int = 16) -> Path:
    flat = name.replace('.vmdk', '-flat.vmdk')
    descriptor = [
        '# Disk DescriptorFile',
        'version=1',
        'CID=fffffffe',
        'parentCID=ffffffff',
        'createType="monolithicFlat"',
        '',
        '# Extent description',
        f'RW {sectors} FLAT "{flat}" 0',
        '',
        '# The Disk Data Base',
        '#DDB',
        'ddb.virtualHWVersion = "4"',
        '',
    ]
    (directory / flat).write_bytes(b'\x00' * (sectors * SECTOR))
    path = directory / name
    path.write_text('\n'.join(descriptor))
    return path


def test_resolve_raw_file(tmp_path: Path):
    image = tmp_path / 'evidence.raw'
    image.write_bytes(b'\x00' * 8192)

    source = SourceResolver().resolve(image)

    assert isinstance(source, FileSource)
    assert source.format == 'raw'


def test_resolve_image_format_override(tmp_path: Path):
    image = tmp_path / 'evidence.bin'
    image.write_bytes(b'random data' * 100)

    source = SourceResolver().resolve(image, image_format='raw')

    assert source.format == 'raw'


def test_resolve_invalid_image_format_raises(tmp_path: Path):
    image = tmp_path / 'evidence.bin'
    image.write_bytes(b'random data' * 100)

    with pytest.raises(NtfsDumpError, match="Unknown image format"):
        SourceResolver().resolve(image, image_format='qcow2')


def test_resolve_vmware_directory(tmp_path: Path):
    _write_vmdk(tmp_path, 'Single.vmdk')
    vmx = [
        '.encoding = "UTF-8"',
        'scsi0:0.present = "TRUE"',
        'scsi0:0.deviceType = "disk"',
        'scsi0:0.fileName = "Single.vmdk"',
        '',
    ]
    (tmp_path / 'SingleVM.vmx').write_text('\n'.join(vmx))

    source = SourceResolver().resolve(tmp_path)

    assert isinstance(source, VmwareSource)
    img_info = source.get_img_info()
    assert img_info.get_size() == 16 * SECTOR
    img_info.close()


def test_resolve_vmdk_file_with_parent_chain(tmp_path: Path):
    base = _write_vmdk(tmp_path, 'Windows.vmdk')
    (tmp_path / 'Windows-000001-flat.vmdk').write_bytes(b'\x00' * (16 * SECTOR))
    child = tmp_path / 'Windows-000001.vmdk'
    child.write_text('\n'.join([
        '# Disk DescriptorFile',
        'version=1',
        'CID=fffffffe',
        'parentCID=fffffffe',
        'createType="monolithicFlat"',
        'parentFileNameHint="Windows.vmdk"',
        '',
        '# Extent description',
        'RW 16 FLAT "Windows-000001-flat.vmdk" 0',
        '',
        '# The Disk Data Base',
        '#DDB',
        'ddb.virtualHWVersion = "4"',
        '',
    ]))

    source = SourceResolver().resolve(child)

    assert isinstance(source, FileSource)
    assert source.format == 'vmdk'
    assert base.exists()
    img_info = source.get_img_info()
    assert img_info.get_size() == 16 * SECTOR
    img_info.close()


def test_single_disk_vm_fixture_resolves(tmp_path: Path):
    source = SourceResolver().resolve(FIXTURES / 'SingleVM')

    assert isinstance(source, VmwareSource)
    assert source.disks[0].path.name == 'Single.vmdk'


def test_resolve_vmware_directory_without_vmx_or_vmsd(tmp_path: Path):
    _write_vmdk(tmp_path, 'disk.vmdk')

    source = SourceResolver().resolve(tmp_path)

    assert isinstance(source, VmwareSource)
    assert [disk.path.name for disk in source.disks] == ['disk.vmdk']
    img_info = source.get_img_info()
    assert img_info.get_size() == 16 * SECTOR
    img_info.close()


def test_snapshot_option_rejected_for_plain_file(tmp_path: Path):
    image = tmp_path / 'evidence.raw'
    image.write_bytes(b'\x00' * 8192)

    with pytest.raises(NtfsDumpError, match="VMware SOURCE"):
        SourceResolver().resolve(image, snapshot='1')
