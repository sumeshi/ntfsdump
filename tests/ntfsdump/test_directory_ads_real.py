"""Directory streams through the real NTFS parser, not fake file objects."""

import struct
import tarfile

import pytsk3
import pytest

from ntfsdump import ntfsdump
from ntfsdump.errors import NtfsDumpError

STREAM_NAME = "review"
STREAM_DATA = b"DIRECTORY ADS CONTENT"
DIRECTORY_RECORD = 50
EXTENSION_RECORD = 100
EXTENSION_SEQUENCE = 1


def _attribute_list_entry(attribute_type, name, lowest_vcn, record, sequence, attr_id):
    encoded_name = name.encode("utf-16-le")
    length = (26 + len(encoded_name) + 7) // 8 * 8
    entry = bytearray(length)
    struct.pack_into(
        "<I H B B Q Q H",
        entry,
        0,
        attribute_type,
        length,
        len(encoded_name) // 2,
        26,
        lowest_vcn,
        (sequence << 48) | record,
        attr_id,
    )
    entry[26 : 26 + len(encoded_name)] = encoded_name
    return entry


def _add_extension_data_attribute(record, data):
    name = "$I30".encode("utf-16-le")
    value_offset = (24 + len(name) + 7) // 8 * 8
    attribute_size = (value_offset + len(data) + 7) // 8 * 8
    attribute = bytearray(attribute_size)
    struct.pack_into(
        "<IIBBHHH",
        attribute,
        0,
        pytsk3.TSK_FS_ATTR_TYPE_NTFS_DATA,
        attribute_size,
        0,
        len(name) // 2,
        24,
        0,
        0,
    )
    struct.pack_into("<IHBB", attribute, 16, len(data), value_offset, 0, 0)
    attribute[24 : 24 + len(name)] = name
    attribute[value_offset : value_offset + len(data)] = data

    # A minimal, allocated MFT extension record with valid update-sequence
    # fixups for its two 512-byte sectors.
    extension = bytearray(1024)
    extension[:4] = b"FILE"
    struct.pack_into("<HH", extension, 4, 48, 3)
    struct.pack_into("<HHHH", extension, 16, EXTENSION_SEQUENCE, 0, 56, 1)
    struct.pack_into("<II", extension, 24, 56 + attribute_size + 8, 1024)
    struct.pack_into("<Q", extension, 32, (2 << 48) | DIRECTORY_RECORD)
    struct.pack_into("<HHI", extension, 40, 1, 0, EXTENSION_RECORD)
    # USA at 48, followed by the original bytes from each sector trailer.
    struct.pack_into("<HHHH", extension, 48, 0xA55A, 3, 0, 0)
    for trailer, replacement in ((510, 50), (1022, 52)):
        struct.pack_into("<H", extension, trailer, 0xA55A)
        struct.pack_into("<H", extension, replacement, 0)
    extension[56 : 56 + attribute_size] = attribute
    struct.pack_into("<II", extension, 56 + attribute_size, 0xFFFFFFFF, 0)
    return extension


def _add_directory_attribute_list(record, stream_name):
    usa_offset = struct.unpack_from("<H", record, 4)[0]
    usa_count = struct.unpack_from("<H", record, 6)[0]
    update_sequence = struct.unpack_from("<H", record, usa_offset)[0]
    for index in range(1, usa_count):
        trailer = index * 512 - 2
        struct.pack_into(
            "<H",
            record,
            trailer,
            struct.unpack_from("<H", record, usa_offset + 2 * index)[0],
        )

    attributes_start = struct.unpack_from("<H", record, 20)[0]
    attributes = []
    position = attributes_start
    while struct.unpack_from("<I", record, position)[0] != 0xFFFFFFFF:
        size = struct.unpack_from("<I", record, position + 4)[0]
        attributes.append(bytearray(record[position : position + size]))
        position += size

    entries = []
    for attribute in attributes:
        attribute_type = struct.unpack_from("<I", attribute)[0]
        name_length = attribute[9]
        name_offset = struct.unpack_from("<H", attribute, 10)[0]
        name = (
            bytes(attribute[name_offset : name_offset + name_length * 2]).decode(
                "utf-16-le"
            )
            if name_length
            else ""
        )
        lowest_vcn = struct.unpack_from("<Q", attribute, 16)[0] if attribute[8] else 0
        attr_id = struct.unpack_from("<H", attribute, 14)[0]
        entries.append(
            _attribute_list_entry(
                attribute_type, name, lowest_vcn, DIRECTORY_RECORD, 2, attr_id
            )
        )

    entries.append(
        _attribute_list_entry(
            pytsk3.TSK_FS_ATTR_TYPE_NTFS_DATA,
            "$I30",
            0,
            EXTENSION_RECORD,
            EXTENSION_SEQUENCE,
            0,
        )
    )
    entries.sort(key=lambda entry: struct.unpack_from("<I", entry)[0])
    value = b"".join(entries)
    value_offset = 24
    attribute_size = (value_offset + len(value) + 7) // 8 * 8
    attr_list = bytearray(attribute_size)
    struct.pack_into("<IIBBHHH", attr_list, 0, 0x20, attribute_size, 0, 0, 0, 0, 1)
    struct.pack_into("<IHBB", attr_list, 16, len(value), value_offset, 0, 0)
    attr_list[value_offset : value_offset + len(value)] = value

    attributes.insert(1, attr_list)
    new_position = attributes_start
    for attribute in attributes:
        record[new_position : new_position + len(attribute)] = attribute
        new_position += len(attribute)
    struct.pack_into("<II", record, new_position, 0xFFFFFFFF, 0)
    struct.pack_into("<I", record, 24, new_position + 8)
    struct.pack_into("<H", record, 40, struct.unpack_from("<H", record, 40)[0] + 1)
    for index in range(1, usa_count):
        trailer = index * 512 - 2
        struct.pack_into(
            "<H",
            record,
            usa_offset + 2 * index,
            struct.unpack_from("<H", record, trailer)[0],
        )
        struct.pack_into("<H", record, trailer, update_sequence)
    return record


def _mft_bitmap_physical_offset(record_zero, logical_offset, cluster_size):
    position = struct.unpack_from("<H", record_zero, 20)[0]
    while struct.unpack_from("<I", record_zero, position)[0] != 0xFFFFFFFF:
        attribute_type, attribute_size = struct.unpack_from(
            "<II", record_zero, position
        )
        if attribute_type == 0xB0:
            assert record_zero[position + 8] == 1
            runlist_offset = struct.unpack_from("<H", record_zero, position + 32)[0]
            runlist = position + runlist_offset
            vcn = 0
            lcn = 0
            while record_zero[runlist]:
                header = record_zero[runlist]
                runlist += 1
                length_size, offset_size = header & 0x0F, header >> 4
                run_length = int.from_bytes(
                    record_zero[runlist : runlist + length_size], "little"
                )
                runlist += length_size
                if offset_size:
                    delta = int.from_bytes(
                        record_zero[runlist : runlist + offset_size],
                        "little",
                        signed=True,
                    )
                    lcn += delta
                    runlist += offset_size
                target_vcn = logical_offset // cluster_size
                if vcn <= target_vcn < vcn + run_length:
                    return (
                        lcn + target_vcn - vcn
                    ) * cluster_size + logical_offset % cluster_size
                vcn += run_length
            raise AssertionError("MFT bitmap runlist does not cover requested byte")
        position += attribute_size
    raise AssertionError("MFT bitmap attribute was not found")


def create_directory_ads_image(prepare_ntfsfile, tmp_path_factory, stream_name):
    # The shared fixture verifies this archive's checksum. Extract a separate
    # sparse copy so neither the cached image nor other tests are modified.
    directory = tmp_path_factory.mktemp("directory-ads")
    with tarfile.open(prepare_ntfsfile.parent / "ntfs.tgs", "r:gz") as archive:
        archive.extract("ntfs.raw", directory, filter="data")
    image = directory / "ntfs.raw"
    native = pytsk3.Img_Info(str(image))
    volumes = pytsk3.Volume_Info(native)
    partition = next(v for v in volumes if v.desc.startswith(b"NTFS"))
    partition_offset = partition.start * volumes.info.block_size
    fs = pytsk3.FS_Info(native, offset=partition_offset)
    entry = fs.open("/test_dir").info.meta.addr
    native.close()

    with image.open("r+b") as disk:
        disk.seek(partition_offset)
        boot = disk.read(512)
        cluster_size = struct.unpack_from("<H", boot, 11)[0] * boot[13]
        mft_offset = (
            partition_offset + struct.unpack_from("<Q", boot, 48)[0] * cluster_size
        )
        record_units = struct.unpack_from("<b", boot, 64)[0]
        record_size = (
            2**-record_units if record_units < 0 else record_units * cluster_size
        )
        record_offset = mft_offset + entry * record_size
        disk.seek(record_offset)
        record = bytearray(disk.read(record_size))
        assert record[:4] == b"FILE"
        position = struct.unpack_from("<H", record, 20)[0]
        while struct.unpack_from("<I", record, position)[0] != 0xFFFFFFFF:
            position += struct.unpack_from("<I", record, position + 4)[0]

        name = stream_name.encode("utf-16-le")
        value_offset = (24 + len(name) + 7) // 8 * 8
        attribute_size = (value_offset + len(STREAM_DATA) + 7) // 8 * 8
        attribute_id = struct.unpack_from("<H", record, 40)[0]
        # The sample's free space is wholly within the second sector, leaving
        # NTFS update-sequence fixups at each sector's final two bytes intact.
        assert position // 512 == (position + attribute_size + 7) // 512
        assert position + attribute_size + 8 <= record_size - 2
        attribute = bytearray(attribute_size)
        struct.pack_into(
            "<IIBBHHH",
            attribute,
            0,
            pytsk3.TSK_FS_ATTR_TYPE_NTFS_DATA,
            attribute_size,
            0,
            len(stream_name),
            24,
            0,
            attribute_id,
        )
        struct.pack_into("<IHBB", attribute, 16, len(STREAM_DATA), value_offset, 0, 0)
        attribute[24 : 24 + len(name)] = name
        attribute[value_offset : value_offset + len(STREAM_DATA)] = STREAM_DATA
        record[position : position + attribute_size] = attribute
        struct.pack_into("<II", record, position + attribute_size, 0xFFFFFFFF, 0)
        struct.pack_into("<I", record, 24, position + attribute_size + 8)
        struct.pack_into("<H", record, 40, attribute_id + 1)
        disk.seek(record_offset)
        disk.write(record)
    return image, partition_offset


def create_directory_index_name_collision_image(prepare_ntfsfile, tmp_path_factory):
    directory = tmp_path_factory.mktemp("directory-index-name-collision")
    with tarfile.open(prepare_ntfsfile.parent / "ntfs.tgs", "r:gz") as archive:
        archive.extract("ntfs.raw", directory, filter="data")
    image = directory / "ntfs.raw"
    native = pytsk3.Img_Info(str(image))
    volumes = pytsk3.Volume_Info(native)
    partition = next(v for v in volumes if v.desc.startswith(b"NTFS"))
    partition_offset = partition.start * volumes.info.block_size
    boot = native.read(partition_offset, 512)
    cluster_size = struct.unpack_from("<H", boot, 11)[0] * boot[13]
    mft_offset = partition_offset + struct.unpack_from("<Q", boot, 48)[0] * cluster_size
    record_units = struct.unpack_from("<b", boot, 64)[0]
    record_size = 2**-record_units if record_units < 0 else record_units * cluster_size
    native.close()

    with image.open("r+b") as disk:
        record_zero_offset = mft_offset
        disk.seek(record_zero_offset)
        record_zero = bytearray(disk.read(record_size))
        bitmap_byte_offset = _mft_bitmap_physical_offset(
            record_zero, EXTENSION_RECORD // 8, cluster_size
        )
        disk.seek(partition_offset + bitmap_byte_offset)
        bitmap_value = disk.read(1)[0]
        disk.seek(partition_offset + bitmap_byte_offset)
        disk.write(bytes([bitmap_value | (1 << (EXTENSION_RECORD % 8))]))

        record_offset = mft_offset + DIRECTORY_RECORD * record_size
        disk.seek(record_offset)
        record = _add_directory_attribute_list(
            bytearray(disk.read(record_size)), "$I30"
        )
        disk.seek(record_offset)
        disk.write(record)

        extension_offset = mft_offset + EXTENSION_RECORD * record_size
        disk.seek(extension_offset)
        disk.write(_add_extension_data_attribute(bytearray(), STREAM_DATA))
    return image, partition_offset


@pytest.fixture(scope="module")
def directory_ads_image(prepare_ntfsfile, tmp_path_factory):
    return create_directory_ads_image(prepare_ntfsfile, tmp_path_factory, STREAM_NAME)


@pytest.mark.parametrize("mode", ["tree", "flat", "file"])
def test_directory_data_stream_extracts_only_requested_bytes(
    directory_ads_image, tmp_path, mode
):
    image, partition_offset = directory_ads_image
    native = pytsk3.Img_Info(str(image))
    fs = pytsk3.FS_Info(native, offset=partition_offset)
    stream = fs.open(f"/test_dir:{STREAM_NAME}")
    assert stream.info.name.type == pytsk3.TSK_FS_NAME_TYPE_DIR
    attribute = next(a for a in stream if a.info.name == STREAM_NAME.encode())
    assert attribute.info.type == pytsk3.TSK_FS_ATTR_TYPE_NTFS_DATA
    assert (
        stream.read_random(
            0, attribute.info.size, attribute.info.type, attribute.info.id
        )
        == STREAM_DATA
    )
    native.close()

    output = tmp_path / ("renamed.bin" if mode == "file" else "out")
    ntfsdump(
        image,
        [f"/test_dir:{STREAM_NAME}"],
        output,
        flat=mode == "flat",
        output_file=mode == "file",
        quiet=True,
    )
    target = output if mode == "file" else output / "test_dir_review"
    assert target.read_bytes() == STREAM_DATA
    assert [p for p in tmp_path.rglob("*") if p.is_file()] == [target]


def test_directory_index_stream_does_not_recurse(prepare_ntfsfile, tmp_path):
    native = pytsk3.Img_Info(str(prepare_ntfsfile))
    volumes = pytsk3.Volume_Info(native)
    partition = next(v for v in volumes if v.desc.startswith(b"NTFS"))
    fs = pytsk3.FS_Info(native, offset=partition.start * volumes.info.block_size)
    stream = fs.open("/test_dir:$I30")
    attribute = next(a for a in stream if a.info.name == b"$I30")
    expected = stream.read_random(
        0, attribute.info.size, attribute.info.type, attribute.info.id
    )
    native.close()

    ntfsdump(prepare_ntfsfile, ["/test_dir:$I30"], tmp_path, quiet=True)
    target = tmp_path / "test_dir_$I30"
    assert target.read_bytes() == expected
    assert list(tmp_path.iterdir()) == [target]


def test_directory_ads_prefers_data_over_same_named_index_attribute(
    prepare_ntfsfile, tmp_path_factory, tmp_path
):
    image, partition_offset = create_directory_index_name_collision_image(
        prepare_ntfsfile, tmp_path_factory
    )
    native = pytsk3.Img_Info(str(image))
    fs = pytsk3.FS_Info(native, offset=partition_offset)
    mft = fs.open("/$MFT")
    bitmap = next(a for a in mft if a.info.type == pytsk3.TSK_FS_ATTR_TYPE_NTFS_BITMAP)
    allocation_byte = mft.read_random(
        EXTENSION_RECORD // 8, 1, bitmap.info.type, bitmap.info.id
    )
    assert allocation_byte[0] & (1 << (EXTENSION_RECORD % 8))

    stream = fs.open("/test_dir:$I30")
    attributes = [a for a in stream if a.info.name == b"$I30"]
    assert attributes[0].info.type == pytsk3.TSK_FS_ATTR_TYPE_NTFS_IDXROOT
    assert attributes[-1].info.type == pytsk3.TSK_FS_ATTR_TYPE_NTFS_DATA
    native.close()

    ntfsdump(image, ["/test_dir:$I30"], tmp_path, quiet=True)
    target = tmp_path / "test_dir_$I30"
    assert target.read_bytes() == STREAM_DATA


def test_missing_directory_stream_is_an_error(directory_ads_image, tmp_path):
    image, _ = directory_ads_image
    with pytest.raises(NtfsDumpError, match="Query path was not found"):
        ntfsdump(image, ["/test_dir:missing"], tmp_path, quiet=True)
    assert not list(tmp_path.iterdir())
