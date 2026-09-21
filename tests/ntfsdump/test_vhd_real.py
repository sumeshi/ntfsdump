# coding: utf-8
"""End-to-end tests using real pyvhdi handles (no mocks).

Minimal dynamic/differential VHD images are crafted on the fly so that the
differencing-disk parent fallback is exercised through the real libvhdi
implementation.
"""
import struct
import uuid
from pathlib import Path

SECTOR = 512
BLOCK_SIZE = 2 * 1024 * 1024
MAX_ENTRIES = 1
MARKER_OFFSET = 64 * SECTOR


def _vhd_checksum(data: bytes) -> int:
    return (~sum(data)) & 0xFFFFFFFF


def _make_footer(disk_type: int, disk_uuid: uuid.UUID) -> bytes:
    f = bytearray(512)
    f[0:8] = b'conectix'
    struct.pack_into('>IIQ', f, 8, 0, 0x00010000, 512)
    f[28:32] = b'ntfs'
    struct.pack_into('>II', f, 32, 0x00010000, 0x00000002)
    struct.pack_into('>QQ', f, 40, BLOCK_SIZE, BLOCK_SIZE)
    struct.pack_into('>HBBH', f, 56, 0xFF, 16, 63, 0)
    struct.pack_into('>I', f, 60, disk_type)  # 3=dynamic 4=differencing
    f[68:84] = disk_uuid.bytes
    struct.pack_into('>I', f, 64, _vhd_checksum(bytes(f)))
    return bytes(f)


def _make_dynamic_header(
    parent_uuid: 'uuid.UUID | None' = None,
    parent_name: str = '',
) -> bytes:
    h = bytearray(1024)
    h[0:8] = b'cxsparse'
    struct.pack_into('>Q', h, 8, 0xFFFFFFFFFFFFFFFF)
    struct.pack_into('>Q', h, 16, 3 * SECTOR)
    struct.pack_into('>II', h, 24, 0x00010000, MAX_ENTRIES)
    struct.pack_into('>I', h, 32, BLOCK_SIZE)
    if parent_uuid is not None:
        h[40:56] = parent_uuid.bytes
    if parent_name:
        encoded = parent_name.encode('utf-16-be')
        h[64:64 + len(encoded)] = encoded
    h[576:580] = b'W2ku'
    struct.pack_into('>I', h, 36, _vhd_checksum(bytes(h)))
    return bytes(h)


def _make_vhd(
    path: Path,
    disk_type: int,
    disk_uuid: uuid.UUID,
    bat_entry: int,
    block_data: bytes,
    parent_uuid: 'uuid.UUID | None' = None,
    parent_name: str = '',
) -> None:
    path.write_bytes(
        _make_footer(disk_type, disk_uuid)
        + _make_dynamic_header(parent_uuid, parent_name)
        + struct.pack('>I', bat_entry)
        + b'\x00' * (SECTOR - 4)
        + b'\xff' * SECTOR
        + block_data
        + _make_footer(disk_type, disk_uuid)
    )


def test_real_vhd_differential_parent_fallback(tmp_path: Path):
    from ntfsdump.formats.vhd import VHDHandler

    base_uuid = uuid.uuid4()
    base_block = bytearray(BLOCK_SIZE)
    base_block[MARKER_OFFSET:MARKER_OFFSET + 10] = b'PARENTDATA'
    _make_vhd(
        tmp_path / 'base.vhd', 3, base_uuid, 4, bytes(base_block),
    )

    # The differencing disk has its block unmapped (BAT = 0xffffffff), so any
    # read must fall back to the parent through set_parent().
    _make_vhd(
        tmp_path / 'child.vhd', 4, uuid.uuid4(), 0xFFFFFFFF, b'\x00' * BLOCK_SIZE,
        parent_uuid=base_uuid, parent_name='base.vhd',
    )

    img_info = VHDHandler().get_img_info(str(tmp_path / 'child.vhd'))
    try:
        assert img_info.get_size() == BLOCK_SIZE
        assert img_info.read(MARKER_OFFSET, 10) == b'PARENTDATA'
    finally:
        img_info.close()
