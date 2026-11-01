# coding: utf-8
"""Regression tests for chunked extraction and EOF handling (NtfsVolume).

dump_files() must stream file data in <= 1 MiB chunks, never swallow a
premature EOF (partial output must be removed), keep ADS ('/file:stream')
queries working, and __read_file() must fail on truncation instead of
returning shorter bytes (ntfsfind reads $MFT through it).
"""

from types import SimpleNamespace
from pathlib import Path

import pytsk3
import pytest

from ntfsdump.errors import NtfsDumpError
from ntfsdump.logger import configure_logging
from ntfsdump.volume import NtfsVolume, BUFF_SIZE


def _pattern(size: int) -> bytes:
    """Deterministic, size-independent content used for both the fake reads
    and the expected on-disk output."""
    block = bytes(range(256))
    return (block * (size // len(block) + 1))[:size]


class FakeAttribute:
    """Duck-typed pytsk3 attribute entry: attribute.info.{name,size,type,id}."""

    def __init__(self, name: bytes, size: int, type: int = 1, id: int = 4):
        self.info = SimpleNamespace(name=name, size=size, type=type, id=id)


class FakeFile:
    """Duck-typed pytsk3.File: info.meta.{addr,size}, info.name.type, an
    iterable of attributes, and a read_random() backing store.

    ``eof_after`` truncates the stream: reads starting at or beyond that
    offset return no data (premature EOF). ``error`` raises from read_random
    when reached, simulating a mid-read I/O failure.
    """

    def __init__(
        self,
        size: int,
        data: bytes,
        attributes=None,
        eof_after: int = None,
        error: Exception = None,
        name_type: int = pytsk3.TSK_FS_NAME_TYPE_REG,
        addr: int = 5,
        fs=None,
        meta: bool = True,
    ):
        self.info = SimpleNamespace(
            meta=SimpleNamespace(addr=addr, size=size) if meta else None,
            name=SimpleNamespace(type=name_type, name=b"fake"),
        )
        self.attributes = list(attributes or [])
        self.data = data
        self.eof_after = eof_after
        self.error = error
        # Reads are logged on the shared FakeFSInfo so that the fresh
        # FakeFile produced by every fs_info.open() keeps contributing to
        # the same call/size accounting.
        self.fs = fs

    def __iter__(self):
        return iter(self.attributes)

    def read_random(self, offset: int, length: int, *args):
        if self.fs is not None:
            self.fs.read_log.append((offset, length, args))
        if self.error is not None and offset >= self.error.offset:
            raise self.error
        if self.eof_after is not None and offset >= self.eof_after:
            return b""
        return self.data[offset : offset + length]


class FakeFSInfo:
    """Duck-typed pytsk3.FS_Info: open() returns a fresh FakeFile per call."""

    def __init__(self):
        self.entries = {}
        self.read_log = []

    def add(self, query: str, **kwargs):
        self.entries[query] = kwargs

    def open(self, query: str):
        kwargs = self.entries.get(query)
        if kwargs is None:
            raise FileNotFoundError(f"No such entry: {query}")
        return FakeFile(fs=self, **kwargs)

    def open_dir(self, query: str):
        """Duck-typed pytsk3.FS_Info.open_dir: list the direct children of
        ``query`` from the registered entries (allocated, live records)."""
        parent = query.rstrip("/")
        for path in self.entries:
            if not path.startswith(parent + "/"):
                continue
            remainder = path[len(parent) + 1 :]
            if not remainder or "/" in remainder:
                continue
            yield SimpleNamespace(
                info=SimpleNamespace(
                    name=SimpleNamespace(
                        name=remainder.encode("utf-8"),
                        flags=pytsk3.TSK_FS_NAME_FLAG_ALLOC,
                        meta_seq=1,
                    ),
                    meta=SimpleNamespace(seq=1),
                ),
            )


def make_volume(tmp_path: Path, fs_info) -> NtfsVolume:
    return NtfsVolume(
        path=tmp_path,
        addr=0,
        description="NTFS",
        start_byte=0,
        end_byte=0,
        fs_info=fs_info,
    )


def test_dump_files_streams_in_chunks_smaller_than_buffer(tmp_path):
    fs = FakeFSInfo()
    size = BUFF_SIZE * 2 + BUFF_SIZE // 2  # 2.5 MiB
    fs.add("/big.bin", size=size, data=_pattern(size))
    vol = make_volume(tmp_path, fs)
    destination = tmp_path / "out"

    vol.dump_files("/big.bin", destination)

    target = destination / "big.bin"
    assert target.exists()
    assert target.read_bytes() == _pattern(size)

    lengths = [length for _, length, _ in fs.read_log]
    # No single read may exceed the 1 MiB buffer (no full-size single read).
    assert max(lengths) <= BUFF_SIZE
    # The stream is pulled chunk-by-chunk: min(BUFF_SIZE, remaining) each time.
    assert lengths == [BUFF_SIZE, BUFF_SIZE, BUFF_SIZE // 2]
    assert len(lengths) == (size + BUFF_SIZE - 1) // BUFF_SIZE


def test_dump_files_premature_eof_raises_and_removes_partial_output(tmp_path):
    fs = FakeFSInfo()
    size = BUFF_SIZE * 3
    eof_after = BUFF_SIZE * 2  # stream dies at ~2/3 of the declared size
    fs.add("/truncated.bin", size=size, data=_pattern(size), eof_after=eof_after)
    vol = make_volume(tmp_path, fs)
    destination = tmp_path / "out"

    with pytest.raises(NtfsDumpError) as excinfo:
        vol.dump_files("/truncated.bin", destination)

    assert "Unexpected EOF" in str(excinfo.value)
    # The partial output (2 MiB were already written) must not survive.
    assert not (destination / "truncated.bin").exists()


def test_dump_files_mid_read_error_removes_partial_output(tmp_path):
    fs = FakeFSInfo()
    size = BUFF_SIZE * 2

    class Boom(IOError):
        offset = BUFF_SIZE  # fail on the second chunk

    fs.add("/boom.bin", size=size, data=_pattern(size), error=Boom("disk went away"))
    vol = make_volume(tmp_path, fs)
    destination = tmp_path / "out"

    # The underlying failure must not be converted into a success (or into
    # a truncated file on disk).
    with pytest.raises(Boom):
        vol.dump_files("/boom.bin", destination)

    assert not (destination / "boom.bin").exists()


@pytest.mark.parametrize("ads", [False, True])
@pytest.mark.parametrize("failure", ["eof", "read_error"])
def test_dump_files_failed_read_preserves_existing_file(tmp_path, ads, failure):
    fs = FakeFSInfo()
    size = BUFF_SIZE * 2

    class Boom(IOError):
        offset = BUFF_SIZE

    query = "/file.bin:zone" if ads else "/file.bin"
    attributes = [FakeAttribute(b"zone", size)] if ads else []
    fs.add(
        query,
        size=size,
        data=_pattern(size),
        attributes=attributes,
        eof_after=BUFF_SIZE if failure == "eof" else None,
        error=Boom("disk went away") if failure == "read_error" else None,
    )
    destination = tmp_path / "out"
    destination.mkdir()
    target = destination / ("file.bin_zone" if ads else "file.bin")
    target.write_bytes(b"existing evidence")

    with pytest.raises(NtfsDumpError if failure == "eof" else Boom):
        make_volume(tmp_path, fs).dump_files(query, destination)

    assert target.read_bytes() == b"existing evidence"
    assert list(destination.iterdir()) == [target]


@pytest.mark.parametrize("data", [b"", b"new evidence"])
@pytest.mark.parametrize("explicit_output", [False, True])
def test_dump_files_success_handles_existing_file(
    tmp_path, data, explicit_output, monkeypatch
):
    fs = FakeFSInfo()
    fs.add("/file.bin", size=len(data), data=data)
    target = tmp_path / "file.bin"
    target.write_bytes(b"existing evidence")
    original_read = FakeFile.read_random

    def read_random(f, *args):
        assert target.read_bytes() == b"existing evidence"
        return original_read(f, *args)

    monkeypatch.setattr(FakeFile, "read_random", read_random)
    make_volume(tmp_path, fs).dump_files(
        "/file.bin",
        target if explicit_output else tmp_path,
    )

    if explicit_output:
        assert target.read_bytes() == data
        assert list(tmp_path.iterdir()) == [target]
    else:
        assert target.read_bytes() == b"existing evidence"
        renamed = tmp_path / "file_5.bin"
        assert renamed.read_bytes() == data
        assert set(tmp_path.iterdir()) == {target, renamed}


@pytest.mark.parametrize("data", [b"", b"new evidence"])
@pytest.mark.parametrize("existing", [False, True])
def test_dump_files_failed_replace_preserves_destination(
    tmp_path, monkeypatch, data, existing
):
    fs = FakeFSInfo()
    fs.add("/file.bin", size=len(data), data=data)
    target = tmp_path / "file.bin"
    if existing:
        target.write_bytes(b"existing evidence")

    def fail_replace(source, destination):
        assert source.read_bytes() == data
        assert destination == target
        raise PermissionError("cannot replace destination")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(PermissionError, match="cannot replace destination"):
        make_volume(tmp_path, fs).dump_files("/file.bin", target, output_file=True)

    if existing:
        assert target.read_bytes() == b"existing evidence"
    assert list(tmp_path.iterdir()) == ([target] if existing else [])


@pytest.mark.parametrize("data", [b"", b"new evidence"])
def test_dump_files_named_output_directory_keeps_fallback(tmp_path, data):
    fs = FakeFSInfo()
    fs.add("/file.bin", size=len(data), data=data)
    destination = tmp_path / "file.bin"
    destination.mkdir()

    make_volume(tmp_path, fs).dump_files("/file.bin", destination)

    target = destination / "file.bin"
    assert target.read_bytes() == data
    assert list(destination.iterdir()) == [target]


@pytest.mark.parametrize("data", [b"", b"new evidence"])
def test_dump_files_directory_at_tree_target_is_preserved(tmp_path, data):
    fs = FakeFSInfo()
    fs.add("/file.bin", size=len(data), data=data)
    target = tmp_path / "file.bin"
    target.mkdir()

    with pytest.raises(
        NtfsDumpError, match="Destination path is an existing directory"
    ):
        make_volume(tmp_path, fs).dump_files("/file.bin", tmp_path)

    assert target.is_dir()
    assert list(tmp_path.iterdir()) == [target]
    assert list(target.iterdir()) == []


def test_dump_files_empty_file_written_without_reads(tmp_path):
    fs = FakeFSInfo()
    fs.add("/empty.bin", size=0, data=b"")
    vol = make_volume(tmp_path, fs)
    destination = tmp_path / "out"

    vol.dump_files("/empty.bin", destination)

    target = destination / "empty.bin"
    assert target.exists()
    assert target.read_bytes() == b""
    assert fs.read_log == []


def test_dump_files_preserves_nested_empty_directories(tmp_path):
    fs = FakeFSInfo()
    for query in ["/parent", "/parent/empty"]:
        fs.add(query, size=0, data=b"", name_type=pytsk3.TSK_FS_NAME_TYPE_DIR)
    destination = tmp_path / "out"
    make_volume(tmp_path, fs).dump_files("/parent", destination)

    assert (destination / "parent" / "empty").is_dir()
    assert not list((destination / "parent" / "empty").iterdir())


def test_empty_directory_cannot_escape_output_via_symlink(tmp_path):
    fs = FakeFSInfo()
    fs.add("/empty", size=0, data=b"", name_type=pytsk3.TSK_FS_NAME_TYPE_DIR)
    destination = tmp_path / "out"
    destination.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (destination / "empty").symlink_to(outside, target_is_directory=True)

    with pytest.raises(NtfsDumpError, match="escapes the destination"):
        make_volume(tmp_path, fs).dump_files("/empty", destination)
    assert not list(outside.iterdir())


def test_flat_mode_does_not_recreate_empty_directories(tmp_path):
    fs = FakeFSInfo()
    fs.add("/empty", size=0, data=b"", name_type=pytsk3.TSK_FS_NAME_TYPE_DIR)
    destination = tmp_path / "out"
    make_volume(tmp_path, fs).dump_files("/empty", destination, flat=True)
    assert not (destination / "empty").exists()


def test_dump_files_alternate_data_stream(tmp_path):
    fs = FakeFSInfo()
    ads_size = BUFF_SIZE + BUFF_SIZE // 2  # 1.5 MiB, spans multiple chunks
    attrs = [FakeAttribute(name=b"zone", size=ads_size, type=1, id=4)]
    fs.add("/file.txt:zone", size=ads_size, data=_pattern(ads_size), attributes=attrs)
    vol = make_volume(tmp_path, fs)
    destination = tmp_path / "out"

    vol.dump_files("/file.txt:zone", destination)

    # Do not assert the sanitized output name exactly (Medium item); just
    # require exactly one file derived from file.txt with matching content.
    targets = [p for p in destination.rglob("*file.txt*") if p.is_file()]
    assert len(targets) == 1
    assert targets[0].read_bytes() == _pattern(ads_size)

    # Every read went through the attribute's type/id, as pytsk3 requires
    # for alternate data streams.
    for _, _, args in fs.read_log:
        assert args == (1, 4)


def test_dump_files_missing_alternate_data_stream_raises(tmp_path):
    fs = FakeFSInfo()
    attrs = [FakeAttribute(name=b"zone", size=BUFF_SIZE, type=1, id=4)]
    fs.add(
        "/file.txt:missing", size=BUFF_SIZE, data=_pattern(BUFF_SIZE), attributes=attrs
    )
    vol = make_volume(tmp_path, fs)

    with pytest.raises(NtfsDumpError) as excinfo:
        vol.dump_files("/file.txt:missing", tmp_path / "out")

    assert "Alternate data stream was not found" in str(excinfo.value)


def test_read_file_returns_complete_bytes(tmp_path):
    # ntfsfind reads $MFT through this API; it must still provide the whole
    # file content when the stream is intact.
    fs = FakeFSInfo()
    size = BUFF_SIZE + BUFF_SIZE // 2  # more than one chunk
    fs.add("/$MFT", size=size, data=_pattern(size))
    vol = make_volume(tmp_path, fs)

    result = vol._NtfsVolume__read_file("/$MFT")

    assert result == _pattern(size)


def test_read_file_premature_eof_raises_not_truncated_bytes(tmp_path):
    fs = FakeFSInfo()
    size = BUFF_SIZE * 2
    fs.add("/$MFT", size=size, data=_pattern(size), eof_after=BUFF_SIZE)
    vol = make_volume(tmp_path, fs)

    with pytest.raises(NtfsDumpError) as excinfo:
        vol._NtfsVolume__read_file("/$MFT")

    assert "Unexpected EOF" in str(excinfo.value)


def test_dump_files_not_found_query_raises_with_query(tmp_path):
    fs = FakeFSInfo()  # open('/nope.bin') raises FileNotFoundError
    vol = make_volume(tmp_path, fs)

    with pytest.raises(NtfsDumpError) as excinfo:
        vol.dump_files("/nope.bin", tmp_path / "out")

    # The failure must surface (never swallowed) and mention the query.
    assert "Query path was not found" in str(excinfo.value)
    assert "/nope.bin" in str(excinfo.value)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "error, expected_message",
    [
        (
            OSError(
                "FS_Info_open: Unable to open file: Invalid API argument "
                "(tsk_fs_file_open: path not found: /file.bin)"
            ),
            "Query path was not found",
        ),
        (OSError("image read failed"), "Unable to read query path"),
        (
            OSError("corrupt metadata: path not found in index"),
            "Unable to read query path",
        ),
        (ValueError("invalid NTFS structure"), "Unable to read query path"),
    ],
)
def test_dump_files_classifies_query_open_errors(
    tmp_path, monkeypatch, error, expected_message
):
    fs = FakeFSInfo()

    def fail_open(query):
        raise error

    monkeypatch.setattr(fs, "open", fail_open)
    with pytest.raises(NtfsDumpError) as excinfo:
        make_volume(tmp_path, fs).dump_files("/file.bin", tmp_path / "out")

    assert str(excinfo.value).startswith(expected_message)
    assert "/file.bin" in str(excinfo.value)
    assert str(error) in str(excinfo.value)
    assert excinfo.value.__cause__ is error
    assert not (tmp_path / "out").exists()


def test_dump_files_entry_without_meta_raises_instead_of_empty_file(tmp_path):
    # A REG entry without MFT metadata must not be dumped as an empty
    # "successful" file (old code crashed loudly; never go silent here).
    fs = FakeFSInfo()
    fs.add("/ghost.bin", size=100, data=_pattern(100), meta=False)
    vol = make_volume(tmp_path, fs)

    with pytest.raises(NtfsDumpError) as excinfo:
        vol.dump_files("/ghost.bin", tmp_path / "out")

    assert "MFT metadata was not found" in str(excinfo.value)
    assert not (tmp_path / "out").exists()


def test_dump_files_flat_joins_directory_names_into_filename(tmp_path):
    # Flat mode joins the whole path into the filename so that same-name
    # files from different directories stay apart
    # (e.g. /a/x.bin -> a_x.bin, /b/x.bin -> b_x.bin).
    fs = FakeFSInfo()
    fs.add("/a/x.bin", size=3, data=b"aaa")
    fs.add("/b/x.bin", size=4, data=b"bbbb")
    fs.add("/root.bin", size=5, data=b"ccccc")
    vol = make_volume(tmp_path, fs)
    destination = tmp_path / "out"

    vol.dump_files("/a/x.bin", destination, flat=True)
    vol.dump_files("/b/x.bin", destination, flat=True)
    vol.dump_files("/root.bin", destination, flat=True)

    outputs = {p.name: p.read_bytes() for p in destination.iterdir()}
    assert outputs == {
        "a_x.bin": b"aaa",
        "b_x.bin": b"bbbb",
        "root.bin": b"ccccc",  # a root-level file keeps its plain name
    }


def test_dump_files_flat_collision_still_gets_unique_suffix(tmp_path):
    # The MFT-entry suffix remains as a backstop when joined flat names
    # still collide (e.g. /a/x.bin vs the literal /a_x.bin).
    fs = FakeFSInfo()
    fs.add("/a/x.bin", size=3, data=b"aaa", addr=20)
    fs.add("/a_x.bin", size=4, data=b"bbbb", addr=21)
    vol = make_volume(tmp_path, fs)
    destination = tmp_path / "out"

    vol.dump_files("/a/x.bin", destination, flat=True)
    vol.dump_files("/a_x.bin", destination, flat=True)

    outputs = {p.name: p.read_bytes() for p in destination.iterdir()}
    assert outputs["a_x.bin"] == b"aaa"
    # The second file was renamed with its MFT entry number, not overwritten.
    assert outputs["a_x_21.bin"] == b"bbbb"


@pytest.mark.parametrize("ads_first", [False, True])
@pytest.mark.parametrize(
    "ads_data, regular_data",
    [
        (b"ADS", b"regular"),
        (b"", b"regular"),
        (b"ADS", b""),
        (b"", b""),
    ],
)
def test_dump_files_tree_ads_name_collision(
    tmp_path, ads_first, ads_data, regular_data
):
    fs = FakeFSInfo()
    ads_query = "/folder/sample.txt:Zone.Identifier"
    regular_query = "/folder/sample.txt_Zone.Identifier"
    fs.add(
        ads_query,
        size=0,
        data=ads_data,
        addr=20,
        attributes=[FakeAttribute(b"Zone.Identifier", len(ads_data))],
    )
    fs.add(regular_query, size=len(regular_data), data=regular_data, addr=21)
    vol = make_volume(tmp_path, fs)
    queries = [ads_query, regular_query] if ads_first else [regular_query, ads_query]
    for query in queries:
        vol.dump_files(query, tmp_path)

    folder = tmp_path / "folder"
    first_data, second_data = (
        (ads_data, regular_data) if ads_first else (regular_data, ads_data)
    )
    second_addr = 21 if ads_first else 20
    outputs = {p.name: p.read_bytes() for p in folder.iterdir()}
    assert outputs == {
        "sample.txt_Zone.Identifier": first_data,
        f"sample.txt_Zone_{second_addr}.Identifier": second_data,
    }


def test_dump_files_flat_ads_embeds_folder_path_and_stream_name(tmp_path):
    ads_size = 100
    attrs = [FakeAttribute(name=b"zone", size=ads_size, type=1, id=4)]
    fs = FakeFSInfo()
    fs.add(
        "/Windows/a.txt:zone",
        size=ads_size,
        data=_pattern(ads_size),
        attributes=attrs,
    )
    vol = make_volume(tmp_path, fs)
    destination = tmp_path / "out"

    vol.dump_files("/Windows/a.txt:zone", destination, flat=True)

    outputs = list(destination.iterdir())
    assert [p.name for p in outputs] == ["Windows_a.txt_zone"]
    assert outputs[0].read_bytes() == _pattern(ads_size)


def test_dump_files_wildcard_expansion_is_reachable(tmp_path):
    # pytsk3 cannot open the literal '.*' path, so the wildcard branch must
    # be checked BEFORE the dir/file probes (it used to be dead code).
    fs = FakeFSInfo()
    fs.add("/data_one.bin", size=3, data=b"aaa")
    fs.add("/data_two.bin", size=4, data=b"bbbb")
    fs.add("/other.bin", size=5, data=b"ccccc")
    fs.add("/data", size=0, data=b"", name_type=pytsk3.TSK_FS_NAME_TYPE_DIR)
    vol = make_volume(tmp_path, fs)
    destination = tmp_path / "out"

    vol.dump_files("/data.*", destination)

    # Only the entries sharing the '/data' prefix were expanded.
    names = sorted(p.name for p in destination.rglob("*") if p.is_file())
    assert names == ["data_one.bin", "data_two.bin"]
    assert (destination / "data_one.bin").read_bytes() == b"aaa"
    assert (destination / "data_two.bin").read_bytes() == b"bbbb"


@pytest.mark.parametrize("query", ["/data/.*", "/data/o.*"])
def test_directory_wildcard_does_not_match_neighboring_directory(tmp_path, query):
    fs = FakeFSInfo()
    for directory in ["/data", "/database"]:
        fs.add(directory, size=0, data=b"", name_type=pytsk3.TSK_FS_NAME_TYPE_DIR)
    fs.add("/data/one.bin", size=3, data=b"one")
    fs.add("/database/other.bin", size=5, data=b"other")

    make_volume(tmp_path, fs).dump_files(query, tmp_path)

    assert (tmp_path / "data" / "one.bin").read_bytes() == b"one"
    assert not (tmp_path / "database").exists()


@pytest.mark.parametrize("data", [b"", b"new"])
def test_directory_named_like_file_preserves_tree(tmp_path, data):
    fs = FakeFSInfo()
    fs.add("/folder/file.bin", size=len(data), data=data)
    destination = tmp_path / "file.bin"
    destination.mkdir()

    make_volume(tmp_path, fs).dump_files("/folder/file.bin", destination)

    assert (destination / "folder" / "file.bin").read_bytes() == data
    assert not (destination / "file.bin").exists()


@pytest.mark.parametrize("data", [b"", b"new"])
@pytest.mark.parametrize("existing", [False, True])
def test_output_file_can_use_a_different_name(tmp_path, data, existing):
    fs = FakeFSInfo()
    fs.add("/folder/file.bin", size=len(data), data=data)
    destination = tmp_path / "renamed.bin"
    if existing:
        destination.write_bytes(b"old")

    make_volume(tmp_path, fs).dump_files(
        "/folder/file.bin", destination, output_file=True
    )

    assert destination.read_bytes() == data
    assert list(tmp_path.iterdir()) == [destination]


def test_log_cannot_alias_file_inside_directory_output(tmp_path):
    fs = FakeFSInfo()
    fs.add(
        "/folder",
        size=0,
        data=b"",
        name_type=pytsk3.TSK_FS_NAME_TYPE_DIR,
    )
    fs.add("/folder/file.bin", size=4, data=b"data")
    destination = tmp_path / "out"
    target = destination / "folder" / "file.bin"
    configure_logging(str(target))

    try:
        with pytest.raises(NtfsDumpError, match="overwrite an extracted file"):
            make_volume(tmp_path, fs).dump_files("/folder", destination)
        assert not target.exists()
    finally:
        configure_logging(None)


@pytest.mark.parametrize("query", ["/folder", "/folder/.*"])
def test_output_file_rejects_directory_and_wildcard_queries(tmp_path, query):
    fs = FakeFSInfo()
    fs.add("/folder", size=0, data=b"", name_type=pytsk3.TSK_FS_NAME_TYPE_DIR)
    destination = tmp_path / "output.bin"
    destination.write_bytes(b"existing evidence")

    with pytest.raises(
        NtfsDumpError, match="File output requires a single file or ADS query"
    ):
        make_volume(tmp_path, fs).dump_files(query, destination, output_file=True)

    assert destination.read_bytes() == b"existing evidence"
