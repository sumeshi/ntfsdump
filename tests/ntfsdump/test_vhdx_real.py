# coding: utf-8
"""End-to-end VHDX/AVHDX tests using real pyvhdi handles (no mocks).

Minimal dynamic + differential VHDX images are crafted byte-by-byte (VHDX
structures: file type identifier, image headers, region tables with CRC-32C,
metadata region with parent locator, BAT) so that the Hyper-V checkpoint
parent fallback is exercised through the real libvhdi implementation.
"""
import struct
import uuid
from pathlib import Path

from pathlib import Path

SECTOR = 512
BLOCK_SIZE = 1024 * 1024
DISK_SIZE = 4 * 1024 * 1024
NUM_BLOCKS = DISK_SIZE // BLOCK_SIZE
PAYLOAD_OFFSET = 3 * 1024 * 1024
METADATA_OFFSET = 1024 * 1024
BAT_OFFSET = 2 * 1024 * 1024

GUID_BAT = bytes([0x66, 0x77, 0xC2, 0x2D, 0x23, 0xF6, 0x00, 0x42,
                  0x9D, 0x64, 0x11, 0x5E, 0x9B, 0xFD, 0x4A, 0x08])
GUID_METADATA = bytes([0x06, 0xA2, 0x7C, 0x8B, 0x90, 0x47, 0x9A, 0x4B,
                       0xB8, 0xFE, 0x57, 0x5F, 0x05, 0x0F, 0x88, 0x6E])
GUID_FILE_PARAMS = bytes([0x37, 0x67, 0xA1, 0xCA, 0x36, 0xFA, 0x43, 0x4D,
                          0xB3, 0xB6, 0x33, 0xF0, 0xAA, 0x44, 0xE7, 0x6B])
GUID_LOGICAL_SECTOR = bytes([0x1D, 0xBF, 0x41, 0x81, 0x6F, 0xA9, 0x09, 0x47,
                             0xBA, 0x47, 0xF2, 0x33, 0xA8, 0xFA, 0xAB, 0x5F])
GUID_PHYSICAL_SECTOR = bytes([0xC7, 0x48, 0xA3, 0xCD, 0x5D, 0x44, 0x71, 0x44,
                              0x9C, 0xC9, 0xE9, 0x88, 0x52, 0x51, 0xC5, 0x56])
GUID_DISK_ID = bytes([0xAB, 0x12, 0xCA, 0xBE, 0xE6, 0xB2, 0x23, 0x45,
                      0x93, 0xEF, 0xC3, 0x09, 0xE0, 0x00, 0xC7, 0x46])
GUID_DISK_SIZE = bytes([0x24, 0x42, 0xA5, 0x2F, 0x1B, 0xCD, 0x76, 0x48,
                        0xB2, 0x11, 0x5D, 0xBE, 0xD8, 0x3B, 0xF4, 0xB8])
GUID_PARENT_LOCATOR_ITEM = bytes([0x2D, 0x5F, 0xD3, 0xA8, 0x0B, 0xB3, 0x4D, 0x45,
                                  0xAB, 0xF7, 0xD3, 0xD8, 0x48, 0x34, 0xAB, 0x0C])
# Parent locator type indicator (b04aefb7-d19e-4fea-b789-25b8e9445913).
GUID_PARENT_LOCATOR_TYPE = bytes([0xB7, 0xEF, 0x4A, 0xB0, 0x9E, 0xD1, 0x81, 0x4A,
                                  0xB7, 0x89, 0x25, 0xB8, 0xE9, 0x44, 0x59, 0x13])


def crc32c(data: bytes) -> int:
    # libvhdi uses CRC-32C (Castagnoli polynomial 0x82f63b78).
    table = []
    for index in range(256):
        checksum = index
        for _ in range(8):
            checksum = (0x82F63B78 ^ (checksum >> 1)) if (checksum & 1) else (checksum >> 1)
        table.append(checksum)
    checksum = 0xFFFFFFFF
    for byte in data:
        checksum = table[(checksum ^ byte) & 0xFF] ^ (checksum >> 8)
    return checksum ^ 0xFFFFFFFF


def crc32(data: bytes) -> int:
    return crc32c(data)


def file_type_identifier() -> bytes:
    return b'vhdxfile' + b'\x00' * 56


def image_header(file_size: int, sequence: int,
                 data_write_uuid: 'uuid.UUID | None' = None) -> bytes:
    h = bytearray(4096)
    h[0:4] = b'head'
    struct.pack_into('<Q', h, 8, sequence)
    h[16:32] = uuid.uuid4().bytes
    # VHDX: set_parent compares the child's parent_linkage GUID against the
    # parent's data write identifier.
    h[32:48] = (data_write_uuid.bytes_le if data_write_uuid
                else uuid.uuid4().bytes)
    h[48:64] = uuid.uuid4().bytes
    struct.pack_into('<H', h, 64, 0)            # log format version
    struct.pack_into('<H', h, 66, 1)            # format version
    struct.pack_into('<I', h, 68, 0)            # log size
    struct.pack_into('<Q', h, 72, 0)            # log offset
    struct.pack_into('<I', h, 4, crc32(bytes(h)))
    return bytes(h)


def region_table(metadata_offset: int, bat_offset: int) -> bytes:
    # libvhdi validates the CRC32 over the whole 64KB region table area
    # (header with checksum zeroed + padding).
    t = bytearray(64 * 1024)
    t[0:4] = b'regi'
    struct.pack_into('<I', t, 8, 2)             # number of entries
    struct.pack_into('<16sQII', t, 16, GUID_METADATA,
                     metadata_offset, 1024 * 1024, 1)
    struct.pack_into('<16sQII', t, 48, GUID_BAT,
                     bat_offset, 1024 * 1024, 1)
    struct.pack_into('<I', t, 4, crc32(bytes(t)))
    return bytes(t)


def parent_locator_item(parent_name: str, parent_uuid: uuid.UUID) -> bytes:
    key0 = 'absolute_win32_path\x00'.encode('utf-16-le')
    key1 = 'parent_linkage\x00'.encode('utf-16-le')
    val0 = parent_name.encode('utf-16-le') + b'\x00\x00'
    val1 = ('{' + str(parent_uuid) + '}\x00').encode('utf-16-le')

    item = bytearray()
    item += GUID_PARENT_LOCATOR_TYPE
    item += struct.pack('<HH', 0, 2)            # reserved, entry count
    base = 20 + 2 * 12                          # 2 entries x 12 bytes
    item += struct.pack('<IIHH', base, base + len(key0), len(key0), len(val0))
    item += struct.pack('<IIHH', base + len(key0) + len(val0),
                        base + len(key0) + len(val0) + len(key1),
                        len(key1), len(val1))
    item += key0 + val0 + key1 + val1
    return bytes(item)


def metadata_region(block_size: int, disk_size: int, disk_uuid: uuid.UUID,
                    differential: bool, parent_item: bytes = b'') -> bytes:
    items = [
        (GUID_FILE_PARAMS,
         struct.pack('<II', block_size, 2 if differential else 0)),
        (GUID_DISK_SIZE, struct.pack('<Q', disk_size)),
        (GUID_LOGICAL_SECTOR, struct.pack('<I', SECTOR)),
        (GUID_PHYSICAL_SECTOR, struct.pack('<I', SECTOR)),
        (GUID_DISK_ID, disk_uuid.bytes_le),
    ]
    if parent_item:
        items.append((GUID_PARENT_LOCATOR_ITEM, parent_item))

    table_size = 32 + 32 * len(items)
    blob = bytearray()
    offsets = []
    # VHDX spec/libvhdi require item offsets to be >= 64KB within the region.
    pos = max(64 * 1024, (table_size + 7) & ~7)
    for guid, data in items:
        offsets.append(pos)
        pos = (pos + len(data) + 7) & ~7

    region = bytearray(1024 * 1024)
    region[0:8] = b'metadata'                    # metadata table header
    struct.pack_into('<H', region, 8, 0)         # reserved
    struct.pack_into('<H', region, 10, len(items))
    entry_offset = 32
    for index, ((guid, data), offset) in enumerate(zip(items, offsets)):
        struct.pack_into('<16sIII', region, entry_offset + 32 * index,
                         guid, offset, len(data), 0)
    start = offsets[0]
    for (guid, data), offset in zip(items, offsets):
        rel = offset - start
        if len(blob) < rel:
            blob += b'\x00' * (rel - len(blob))
        blob += data
    region[start:start + len(blob)] = blob
    return bytes(region)


def bat_region(entries):
    bat = bytearray(1024 * 1024)
    for index, entry in enumerate(entries):
        struct.pack_into('<Q', bat, 8 * index, entry)
    return bytes(bat)


def make_vhdx(path: Path, disk_uuid: uuid.UUID, differential: bool,
              parent_name: str = '', parent_uuid: uuid.UUID = None,
              marker: bool = False,
              data_write_uuid: 'uuid.UUID | None' = None) -> None:
    f = bytearray()
    f += file_type_identifier()
    f += b'\x00' * (0x10000 - len(f))
    f += image_header(0, 1, data_write_uuid)     # placeholder file size
    f += b'\x00' * (0x20000 - len(f))
    f += image_header(0, 2, data_write_uuid)
    f += b'\x00' * (0x30000 - len(f))
    f += region_table(METADATA_OFFSET, BAT_OFFSET)
    f += b'\x00' * (0x40000 - len(f))
    f += region_table(METADATA_OFFSET, BAT_OFFSET)
    f += b'\x00' * (METADATA_OFFSET - len(f))

    if differential:
        locator = parent_locator_item(parent_name, parent_uuid)
        f += metadata_region(BLOCK_SIZE, DISK_SIZE, disk_uuid, True, locator)
        f += bat_region([0] * NUM_BLOCKS)
    else:
        f += metadata_region(BLOCK_SIZE, DISK_SIZE, disk_uuid, False)
        entries = [(PAYLOAD_OFFSET // (1024 * 1024) + i) << 20 | 6
                   for i in range(NUM_BLOCKS)]
        f += bat_region(entries)
        f += b'\x00' * (PAYLOAD_OFFSET - len(f))
        for i in range(NUM_BLOCKS):
            block = bytearray(BLOCK_SIZE)
            if marker and i == 0:
                block[128 * 1024:128 * 1024 + 10] = b'PARENTDATA'
            f += bytes(block)

    path.write_bytes(bytes(f))


def test_real_vhdx_differential_parent_fallback(tmp_path: Path):
    from ntfsdump.formats.vhd import VHDHandler

    base_uuid = uuid.uuid4()
    make_vhdx(
        tmp_path / 'base.vhdx', base_uuid, False, marker=True,
        data_write_uuid=base_uuid,
    )
    make_vhdx(
        tmp_path / 'diff.avhdx', uuid.uuid4(), True,
        parent_name='base.vhdx', parent_uuid=base_uuid,
    )

    img_info = VHDHandler().get_img_info(str(tmp_path / 'diff.avhdx'))
    try:
        assert img_info.get_size() == 4 * 1024 * 1024
        assert img_info.read(128 * 1024, 10) == b'PARENTDATA'
    finally:
        img_info.close()
