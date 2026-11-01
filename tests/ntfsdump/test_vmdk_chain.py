# coding: utf-8
from pathlib import Path
import struct

import pytest

from ntfsdump.errors import NtfsDumpError
from ntfsdump.formats.vmdk import (
    VMDKHandler, _resolve_parent, open_vmdk_chain, probe_media_size,
)

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


@pytest.mark.parametrize('output_name', [
    'child.vmdk', 'child-flat.vmdk', 'parent.vmdk', 'parent-flat.vmdk',
])
def test_extraction_cannot_replace_vmdk_backing_files(tmp_path, monkeypatch, output_name):
    from types import SimpleNamespace
    from ntfsdump.core import ntfsdump
    from ntfsdump.image import ImageFile

    _descriptor(tmp_path, 'parent.vmdk', [(16, 'parent-flat.vmdk')])
    child = _descriptor(
        tmp_path, 'child.vmdk', [(16, 'child-flat.vmdk')], parent='parent.vmdk',
    )
    output = tmp_path / output_name
    original = output.read_bytes()
    # Open the real VMDK chain; a tiny fixture has no NTFS filesystem.
    monkeypatch.setattr(
        ImageFile, '_ImageFile__analyze_partitions',
        lambda self: [SimpleNamespace(addr=0, description='NTFS')],
    )
    with pytest.raises(NtfsDumpError, match='overwrite an input image'):
        ntfsdump(child, ['/$MFT'], output=output, quiet=True)
    assert output.read_bytes() == original


@pytest.mark.parametrize('log_name', ['parent.vmdk', 'parent-flat.vmdk'])
def test_log_cannot_modify_vmdk_backing_files(tmp_path, capsys, log_name):
    from ntfsdump.cli import main

    _descriptor(tmp_path, 'parent.vmdk', [(16, 'parent-flat.vmdk')])
    child = _descriptor(
        tmp_path, 'child.vmdk', [(16, 'child-flat.vmdk')], parent='parent.vmdk',
    )
    log = tmp_path / log_name
    original = log.read_bytes()

    assert main([str(child), '/$MFT', '--log', str(log)]) == 1
    assert 'overwrite an input image' in capsys.readouterr().err
    assert log.read_bytes() == original


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


@pytest.mark.parametrize('hint', [
    'C:\\original\\base.vmdk', 'C:base.vmdk',
    '\\\\server\\share\\base.vmdk', '//server/share/base.vmdk',
    '/original/base.vmdk',
])
def test_absolute_parent_hints_only_probe_local_paths(tmp_path, monkeypatch, hint):
    local = tmp_path / 'base.vmdk'
    local.touch()
    original_stat = Path.stat

    def local_stat(path, *args, **kwargs):
        assert path.is_relative_to(tmp_path), f'External path probed: {path}'
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'stat', local_stat)
    assert _resolve_parent(tmp_path / 'child.vmdk', hint, tmp_path) == local


def test_posix_absolute_parent_prefers_collected_local_disk(tmp_path):
    evidence = tmp_path / 'evidence'
    outside = tmp_path / 'outside'
    evidence.mkdir()
    outside.mkdir()
    external = _descriptor(outside, 'base.vmdk', [(16, 'base-flat.vmdk')])
    local = _descriptor(evidence, 'base.vmdk', [(16, 'base-flat.vmdk')])
    child = _descriptor(
        evidence, 'child.vmdk', [(16, 'child-flat.vmdk')], parent=str(external),
    )

    assert _resolve_parent(child, str(external), evidence) == local
    assert len(open_vmdk_chain(child).handles) == 2


def test_absolute_parent_without_local_copy_is_rejected(tmp_path):
    evidence = tmp_path / 'evidence'
    outside = tmp_path / 'outside'
    evidence.mkdir()
    outside.mkdir()
    external = _descriptor(outside, 'base.vmdk', [(16, 'base-flat.vmdk')])
    child = _descriptor(
        evidence, 'child.vmdk', [(16, 'child-flat.vmdk')], parent=str(external),
    )

    with pytest.raises(NtfsDumpError, match='Parent VMDK was not found'):
        open_vmdk_chain(child)


def test_parent_path_junction_is_not_followed(tmp_path, monkeypatch):
    nested = tmp_path / 'nested'
    nested.mkdir()
    (nested / 'base.vmdk').touch()
    monkeypatch.setattr(Path, 'is_junction', lambda path: path == nested)

    with pytest.raises(NtfsDumpError, match='Parent VMDK was not found'):
        _resolve_parent(tmp_path / 'child.vmdk', 'nested/base.vmdk', tmp_path)


@pytest.mark.parametrize('hint', [
    '../outside/base.vmdk', 'file-link.vmdk', 'directory-link/base.vmdk',
])
def test_parent_references_cannot_escape_initial_directory(tmp_path, hint):
    evidence = tmp_path / 'evidence'
    outside = tmp_path / 'outside'
    evidence.mkdir()
    outside.mkdir()
    external = _descriptor(outside, 'base.vmdk', [(16, 'base-flat.vmdk')])
    (evidence / 'file-link.vmdk').symlink_to(external)
    (evidence / 'directory-link').symlink_to(outside, target_is_directory=True)
    child = _descriptor(
        evidence, 'child.vmdk', [(16, 'child-flat.vmdk')], parent=hint,
    )

    with pytest.raises(NtfsDumpError, match='Parent VMDK was not found'):
        open_vmdk_chain(child)


def test_parent_chain_keeps_initial_directory_scope(tmp_path):
    nested = tmp_path / 'nested'
    nested.mkdir()
    _descriptor(tmp_path, 'base.vmdk', [(16, 'base-flat.vmdk')])
    _descriptor(
        nested, 'parent.vmdk', [(16, 'parent-flat.vmdk')], parent='../base.vmdk',
    )
    child = _descriptor(
        tmp_path, 'child.vmdk', [(16, 'child-flat.vmdk')], parent='nested/parent.vmdk',
    )

    assert len(open_vmdk_chain(child).handles) == 3


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


@pytest.mark.parametrize('reference', ['../outside-flat.vmdk', '/outside-flat.vmdk'])
def test_external_extent_reference_is_rejected(tmp_path, reference):
    descriptor = _descriptor(tmp_path, 'base.vmdk', [(16, 'local-flat.vmdk')])
    descriptor.write_text(descriptor.read_text().replace('local-flat.vmdk', reference))

    with pytest.raises(NtfsDumpError, match='escapes the image directory'):
        open_vmdk_chain(descriptor)


def test_extent_symlink_cannot_read_external_data(tmp_path):
    evidence = tmp_path / 'evidence'
    evidence.mkdir()
    external = tmp_path / 'outside-flat.vmdk'
    external.write_bytes(b'OUTSIDE!' + b'\0' * (8192 - 8))
    descriptor = _descriptor(evidence, 'base.vmdk', [(16, 'base-flat.vmdk')])
    extent = evidence / 'base-flat.vmdk'
    extent.rename(evidence / 'saved-flat.vmdk')
    extent.symlink_to(external)

    with pytest.raises(NtfsDumpError, match='symlink or junction'):
        open_vmdk_chain(descriptor)


def test_extent_subdirectory_and_cleanup(tmp_path):
    (tmp_path / 'data').mkdir()
    descriptor = _descriptor(tmp_path, 'base.vmdk', [(16, 'data/base-flat.vmdk')])
    extent = tmp_path / 'data' / 'base-flat.vmdk'
    extent.write_bytes(b'LOCAL!' + b'\0' * (8192 - 6))
    image = VMDKHandler().get_img_info(str(descriptor))
    files = [resource for resource in image._keepalive if hasattr(resource, 'closed')]
    try:
        assert image.read(0, 6) == b'LOCAL!'
    finally:
        image.close()
    assert files and all(file.closed for file in files)


def test_failed_extent_validation_closes_already_opened_files(tmp_path, monkeypatch):
    descriptor = _descriptor(tmp_path, 'base.vmdk', [
        (16, 'first-flat.vmdk'), (16, 'second-flat.vmdk'),
    ])
    descriptor.write_text(descriptor.read_text().replace('second-flat.vmdk', '../outside-flat.vmdk'))
    opened = []
    original_open = Path.open

    def track_open(path, *args, **kwargs):
        file = original_open(path, *args, **kwargs)
        opened.append(file)
        return file

    monkeypatch.setattr(Path, 'open', track_open)
    with pytest.raises(NtfsDumpError, match='escapes the image directory'):
        open_vmdk_chain(descriptor)
    assert opened and all(file.closed for file in opened)


@pytest.mark.parametrize('filename', ['disk.vmdk', 'renamed.vmdk'])
def test_monolithic_sparse_extent_remains_readable(tmp_path, filename):
    # One allocated grain with an embedded descriptor and redundant grain tables.
    path = tmp_path / filename
    data = bytearray(256 * SECTOR)
    struct.pack_into('<IIIQQQQIQQQ', data, 0,
                     0x564d444b, 1, 3, 128, 128, 1, 1, 512, 2, 3, 128)
    data[72:77] = bytes([0, 10, 32, 13, 10])
    descriptor = (
        '# Disk DescriptorFile\nversion=1\nCID=fffffffe\nparentCID=ffffffff\n'
        'createType="monolithicSparse"\n\n# Extent description\n'
        'RW 128 SPARSE "disk.vmdk"\n\n# The Disk Data Base\n#DDB\n'
        'ddb.virtualHWVersion = "4"\n'
    ).encode()
    data[SECTOR:SECTOR + len(descriptor)] = descriptor
    for sector, value in [(2, 4), (3, 8), (4, 128), (8, 128)]:
        struct.pack_into('<I', data, sector * SECTOR, value)
    data[128 * SECTOR:128 * SECTOR + 7] = b'SPARSE!'
    path.write_bytes(data)

    image = VMDKHandler().get_img_info(str(path))
    try:
        assert image.read(0, 7) == b'SPARSE!'
        assert image.read(7, 16) == b'\0' * 16
    finally:
        image.close()
