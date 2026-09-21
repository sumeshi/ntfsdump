# coding: utf-8
from pathlib import Path

import pytest

from ntfsdump.errors import NtfsDumpError
from ntfsdump.formats.vmdk import VMDKHandler, open_vmdk_chain, probe_media_size

SECTOR = 512


def _descriptor(
    directory: Path,
    name: str,
    extents,
    parent: str = None,
) -> Path:
    lines = [
        '# Disk DescriptorFile',
        'version=1',
        'CID=fffffffe',
        f'parentCID={"fffffffe" if parent else "ffffffff"}',
        'createType="monolithicFlat"',
    ]
    if parent:
        lines.append(f'parentFileNameHint="{parent}"')
    lines.append('')
    lines.append('# Extent description')
    for sectors, extent_name in extents:
        lines.append(f'RW {sectors} FLAT "{extent_name}" 0')
    lines.append('')
    lines.append('# The Disk Data Base')
    lines.append('#DDB')
    lines.append('ddb.virtualHWVersion = "4"')
    lines.append('')

    path = directory / name
    path.write_text('\n'.join(lines))
    for sectors, extent_name in extents:
        (directory / extent_name).write_bytes(b'\x00' * (sectors * SECTOR))
    return path


def test_base_only(tmp_path: Path):
    base = _descriptor(tmp_path, 'Windows.vmdk', [(16, 'Windows-flat.vmdk')])
    chain = open_vmdk_chain(base)

    assert len(chain.handles) == 1
    assert chain.handle.get_media_size() == 16 * SECTOR


def test_base_plus_child(tmp_path: Path):
    _descriptor(tmp_path, 'Windows.vmdk', [(16, 'Windows-flat.vmdk')])
    child = _descriptor(
        tmp_path,
        'Windows-000001.vmdk',
        [(16, 'Windows-000001-flat.vmdk')],
        parent='Windows.vmdk',
    )
    chain = open_vmdk_chain(child)

    assert len(chain.handles) == 2
    assert chain.handle.get_media_size() == 16 * SECTOR


def test_base_plus_multiple_children(tmp_path: Path):
    base = _descriptor(tmp_path, 'Windows.vmdk', [(16, 'Windows-flat.vmdk')])
    first = _descriptor(
        tmp_path, 'Windows-000001.vmdk',
        [(16, 'Windows-000001-flat.vmdk')], parent='Windows.vmdk',
    )
    second = _descriptor(
        tmp_path, 'Windows-000002.vmdk',
        [(16, 'Windows-000002-flat.vmdk')], parent='Windows-000001.vmdk',
    )

    assert len(open_vmdk_chain(base).handles) == 1
    assert len(open_vmdk_chain(first).handles) == 2
    assert len(open_vmdk_chain(second).handles) == 3


def test_missing_parent_raises(tmp_path: Path):
    child = _descriptor(
        tmp_path,
        'Windows-000001.vmdk',
        [(16, 'Windows-000001-flat.vmdk')],
        parent='Windows.vmdk',
    )

    with pytest.raises(NtfsDumpError, match="Parent VMDK was not found: Windows.vmdk"):
        open_vmdk_chain(child)


def test_circular_parent_raises(tmp_path: Path):
    _descriptor(
        tmp_path, 'a.vmdk', [(16, 'a-flat.vmdk')], parent='b.vmdk',
    )
    _descriptor(
        tmp_path, 'b.vmdk', [(16, 'b-flat.vmdk')], parent='a.vmdk',
    )

    with pytest.raises(NtfsDumpError, match="Circular VMDK parent reference"):
        open_vmdk_chain(tmp_path / 'a.vmdk')


def test_split_extent_descriptor(tmp_path: Path):
    descriptor = _descriptor(
        tmp_path,
        'Windows.vmdk',
        [(16, 'Windows-s001.vmdk'), (16, 'Windows-s002.vmdk')],
    )
    chain = open_vmdk_chain(descriptor)

    assert chain.handle.get_media_size() == 32 * SECTOR
    assert len(chain.handles) == 1


def test_vmdk_handler_reads_logical_disk(tmp_path: Path):
    base = _descriptor(tmp_path, 'Windows.vmdk', [(8, 'Windows-flat.vmdk')])
    handler = VMDKHandler()
    img_info = handler.get_img_info(str(base))

    assert img_info.get_size() == 8 * SECTOR
    assert img_info.read(0, 4) == b'\x00\x00\x00\x00'
    img_info.close()


def test_probe_media_size_returns_none_for_missing(tmp_path: Path):
    assert probe_media_size(tmp_path / 'missing.vmdk') is None
