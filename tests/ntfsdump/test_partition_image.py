"""Partition-only images must work without a partition table."""

import hashlib
import struct
import uuid
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytsk3
import pytest

from ntfsdump.core import ntfsdump
from ntfsdump.errors import NtfsDumpError
from ntfsdump.formats.base import BaseImgInfo
from ntfsdump.image import ImageFile


def _gpt_header(
    current_lba, backup_lba, first_usable, last_usable, entries_lba, entries_crc, disk_id
):
    header = bytearray(512)
    struct.pack_into(
        "<8sIIIIQQQQ16sQIII",
        header,
        0,
        b"EFI PART",
        0x00010000,
        92,
        0,
        0,
        current_lba,
        backup_lba,
        first_usable,
        last_usable,
        disk_id.bytes_le,
        entries_lba,
        128,
        128,
        entries_crc,
    )
    struct.pack_into("<I", header, 16, zlib.crc32(header[:92]) & 0xFFFFFFFF)
    return bytes(header)


def _make_gpt_with_evidence_label(source, destination, target_sector_size=None):
    source_img = pytsk3.Img_Info(str(source))
    try:
        table = pytsk3.Volume_Info(source_img)
        partition = next(p for p in table if p.desc.startswith(b"NTFS"))
        source_sector_size = table.info.block_size
        sector_size = target_sector_size or source_sector_size
        partition_bytes = partition.len * source_sector_size
        assert partition_bytes % sector_size == 0
        partition_length = partition_bytes // sector_size
        first_lba = 256 if sector_size == 4096 else 2048
        total_sectors = first_lba + partition_length + 2048
        last_lba = first_lba + partition_length - 1
        disk_id = uuid.uuid4()

        entries = bytearray(128 * 128)
        basic_data_guid = uuid.UUID("ebd0a0a2-b9e5-4433-87c0-68b6b72699c7")
        struct.pack_into(
            "<16s16sQQQ72s",
            entries,
            0,
            basic_data_guid.bytes_le,
            uuid.uuid4().bytes_le,
            first_lba,
            last_lba,
            0,
            "Evidence".encode("utf-16-le").ljust(72, b"\0"),
        )
        entries_crc = zlib.crc32(entries) & 0xFFFFFFFF
        backup_entries_lba = total_sectors - 33
        filesystem = pytsk3.FS_Info(
            source_img,
            partition.start * source_sector_size,
            pytsk3.TSK_FS_TYPE_NTFS,
        )
        ranges = [(0, 1024 * 1024), (partition_length * sector_size - sector_size, sector_size)]
        for query in ("/$MFT", "/"):
            for attribute in filesystem.open(query):
                for run in attribute:
                    if run.addr:
                        ranges.append(
                            (
                                run.addr * filesystem.info.block_size,
                                run.len * filesystem.info.block_size,
                            )
                        )

        protective_mbr = bytearray(512)
        protective_mbr[446 + 4] = 0xEE
        struct.pack_into("<II", protective_mbr, 446 + 8, 1, min(total_sectors - 1, 0xFFFFFFFF))
        protective_mbr[510:512] = b"\x55\xaa"
        with destination.open("wb") as output:
            output.truncate(total_sectors * sector_size)
            output.seek(0)
            output.write(protective_mbr)
            output.seek(sector_size)
            output.write(
                _gpt_header(
                    1,
                    total_sectors - 1,
                    34,
                    total_sectors - 34,
                    2,
                    entries_crc,
                    disk_id,
                )
            )
            output.seek(2 * sector_size)
            output.write(entries)
            output.seek(backup_entries_lba * sector_size)
            output.write(entries)
            output.seek((total_sectors - 1) * sector_size)
            output.write(
                _gpt_header(
                    total_sectors - 1,
                    1,
                    34,
                    total_sectors - 34,
                    backup_entries_lba,
                    entries_crc,
                    disk_id,
                )
            )
            for partition_offset, length in ranges:
                source_offset = partition.start * source_sector_size + (
                    partition_offset
                )
                output.seek(first_lba * sector_size + partition_offset)
                remaining = length
                while remaining:
                    chunk = source_img.read(source_offset, min(1024 * 1024, remaining))
                    assert chunk
                    output.write(chunk)
                    source_offset += len(chunk)
                    remaining -= len(chunk)
    finally:
        source_img.close()


@pytest.fixture
def partition_image(prepare_ntfsfile, tmp_path):
    image = pytsk3.Img_Info(str(prepare_ntfsfile))
    try:
        table = pytsk3.Volume_Info(image)
        partition = next(p for p in table if p.desc.startswith(b"NTFS"))
        sector = table.info.block_size
        start = partition.start * sector
        length = partition.len * sector
        fs = pytsk3.FS_Info(image, start, pytsk3.TSK_FS_TYPE_NTFS)
        # Keep the real boot sector, MFT and root index at their original
        # offsets; the rest of this test image is sparse unused space.
        ranges = [(0, 1024 * 1024), (length - sector, sector)]
        for query in ("/$MFT", "/"):
            for attribute in fs.open(query):
                for run in attribute:
                    if run.addr:
                        ranges.append(
                            (run.addr * fs.info.block_size, run.len * fs.info.block_size)
                        )
        destination = tmp_path / "partition.raw"
        with Path(prepare_ntfsfile).open("rb") as source, destination.open("wb") as out:
            out.truncate(length)
            for offset, size in ranges:
                source.seek(start + offset)
                out.seek(offset)
                remaining = size
                while remaining:
                    data = source.read(min(remaining, 1024 * 1024))
                    assert data
                    out.write(data)
                    remaining -= len(data)
        return destination
    finally:
        image.close()


def test_real_partition_extraction(partition_image, tmp_path):
    output = tmp_path / "mft.bin"
    ntfsdump(
        partition_image, ["/$MFT"], output=output, output_file=True, quiet=True
    )
    assert hashlib.md5(output.read_bytes()).hexdigest() == "edb7605e808ec25c8e5feea382a49047"


def test_real_partition_selection(partition_image):
    image = ImageFile(partition_image, volume=0)
    try:
        assert image.main_volume.addr == 0
        assert image.main_volume.fs_info.open("/$MFT").info.meta.size == 262144
    finally:
        image.img_info.close()
    with pytest.raises(NtfsDumpError, match="NTFS volume 2 was not found"):
        ImageFile(partition_image, volume=2)


def test_real_gpt_partition_with_user_label_is_probed(prepare_ntfsfile, tmp_path):
    path = tmp_path / "gpt-evidence.raw"
    _make_gpt_with_evidence_label(prepare_ntfsfile, path)
    native = pytsk3.Img_Info(str(path))
    try:
        table = pytsk3.Volume_Info(native)
        partition = next(p for p in table if p.flags == pytsk3.TSK_VS_PART_FLAG_ALLOC)
        assert partition.desc == b"Evidence"
        assert pytsk3.FS_Info(
            native, partition.start * table.info.block_size, pytsk3.TSK_FS_TYPE_NTFS
        ).open("/test_dir/file_1.txt").read_random(0, 16) == b"file_1"
    finally:
        native.close()

    image = ImageFile(path, volume=partition.addr)
    try:
        assert image.main_volume.description == "Evidence"
        file = image.main_volume.fs_info.open("/test_dir/file_1.txt")
        assert file.read_random(0, 16) == b"file_1"
    finally:
        image.img_info.close()


def test_unknown_backend_sector_keeps_gpt_4kn_autodetection(
    prepare_ntfsfile, tmp_path
):
    path = tmp_path / "gpt-4kn.raw"
    _make_gpt_with_evidence_label(prepare_ntfsfile, path, target_sector_size=4096)

    class FileHandle:
        def __init__(self, image_path):
            self.file = image_path.open("rb")

        def seek(self, offset):
            self.file.seek(offset)

        def read(self, size):
            return self.file.read(size)

        def get_media_size(self):
            return path.stat().st_size

        def close(self):
            self.file.close()

    info = BaseImgInfo(FileHandle(path))
    try:
        table = pytsk3.Volume_Info(info)
        assert table.info.block_size == 4096
        partition = next(p for p in table if p.flags == pytsk3.TSK_VS_PART_FLAG_ALLOC)
        assert partition.desc == b"Evidence"
        assert partition.start == 256
        assert info.logical_sector_size is None
    finally:
        info.close()


@pytest.mark.parametrize("table_raises", [True, False])
def test_partition_probe_requires_native_ntfs(monkeypatch, tmp_path, table_raises):
    image = ImageFile.__new__(ImageFile)
    image.img_info = SimpleNamespace(get_size=lambda: 4096)
    image.resolved = SimpleNamespace(path=tmp_path / "volume.raw", format="raw")
    image.block_size = 512

    class EmptyTable(list):
        info = SimpleNamespace(block_size=512)

    def volume_info(_):
        if table_raises:
            raise OSError("No partition table")
        return EmptyTable()

    def not_ntfs(*args):
        raise OSError("Not an NTFS filesystem")

    monkeypatch.setattr(pytsk3, "Volume_Info", volume_info)
    monkeypatch.setattr(pytsk3, "FS_Info", not_ntfs)
    with pytest.raises(NtfsDumpError, match="No NTFS volume was found"):
        image._ImageFile__analyze_partitions()


def test_empty_partition_table_can_still_have_offset_zero_ntfs(monkeypatch, tmp_path):
    image = ImageFile.__new__(ImageFile)
    image.img_info = SimpleNamespace(get_size=lambda: 4096)
    image.resolved = SimpleNamespace(path=tmp_path / "volume.raw", format="raw")
    image.block_size = 512

    class EmptyTable(list):
        info = SimpleNamespace(block_size=512)

    fs = object()
    monkeypatch.setattr(pytsk3, "Volume_Info", lambda _: EmptyTable())

    def fs_info(img, offset, fs_type):
        assert offset == 0
        assert fs_type == pytsk3.TSK_FS_TYPE_NTFS
        return fs

    monkeypatch.setattr(pytsk3, "FS_Info", fs_info)
    result = image._ImageFile__analyze_partitions()
    assert len(result) == 1
    assert result[0].addr == 0
    assert result[0].fs_info is fs


def test_partition_scan_probes_allocated_partitions_by_filesystem(monkeypatch, tmp_path):
    image = ImageFile.__new__(ImageFile)
    image.img_info = SimpleNamespace(get_size=lambda: 4096)
    image.resolved = SimpleNamespace(path=tmp_path / "disk.raw", format="raw")
    image.block_size = 512

    class Part:
        addr = 4
        start = 2048
        len = 128
        flags = pytsk3.TSK_VS_PART_FLAG_ALLOC
        desc = b"Evidence"

    class Table(list):
        info = SimpleNamespace(block_size=512)

    fs = object()
    requested_offsets = []
    monkeypatch.setattr(pytsk3, "Volume_Info", lambda _: Table([Part()]))

    def fs_info(img, offset, fs_type):
        requested_offsets.append(offset)
        return fs

    monkeypatch.setattr(pytsk3, "FS_Info", fs_info)
    result = image._ImageFile__analyze_partitions()
    assert requested_offsets == [2048 * 512]
    assert [(item.addr, item.description) for item in result] == [(4, "Evidence")]


def test_partition_scan_uses_backend_4kn_sector_size(monkeypatch, tmp_path):
    image = ImageFile.__new__(ImageFile)
    image.img_info = SimpleNamespace(
        get_size=lambda: 4 * 1024 * 1024, logical_sector_size=4096
    )
    image.resolved = SimpleNamespace(path=tmp_path / "disk.vhdx", format="vhd")
    image.block_size = 512

    class Part:
        addr = 2
        start = 256
        len = 768
        flags = pytsk3.TSK_VS_PART_FLAG_ALLOC
        desc = b"NTFS / exFAT (0x07)"

    class Table(list):
        info = SimpleNamespace(block_size=512)

    fs = object()
    requested_offsets = []
    monkeypatch.setattr(pytsk3, "Volume_Info", lambda _: Table([Part()]))

    def fs_info(img, offset, fs_type):
        requested_offsets.append(offset)
        return fs

    monkeypatch.setattr(pytsk3, "FS_Info", fs_info)
    result = image._ImageFile__analyze_partitions()
    assert requested_offsets == [256 * 4096]
    assert result[0].start_byte == 256
