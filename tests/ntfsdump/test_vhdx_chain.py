# coding: utf-8
from pathlib import Path

import pytest

import ntfsdump.formats.vhd as vhd
from ntfsdump.errors import NtfsDumpError
from ntfsdump.formats.vhd import VHDHandler, open_vhdx_chain

VHDX_HEADER = b'vhdxfile' + b'\x00' * 64
VHD_HEADER = b'\x00' * 64


class FakeVhdiFile:
    files = {}

    def __init__(self):
        self._rec = None

    def open(self, path, mode='r'):
        self._rec = self.files[str(Path(path).resolve())]

    def get_parent_filename(self):
        return self._rec.get("parent_filename")

    def get_identifier(self):
        return self._rec.get("identifier")

    def get_parent_identifier(self):
        return self._rec.get("parent_identifier")

    def get_media_size(self):
        return self._rec.get("media_size", 0)

    def set_parent(self, parent):
        if self._rec.get("parent_identifier") != parent.get_identifier():
            raise OSError("mismatch in parent identifier")
        self._parent = parent

    def seek(self, offset):
        pass

    def read(self, size):
        return b"\x00" * size

    def close(self):
        pass


@pytest.fixture
def fake_vhdi(monkeypatch):
    FakeVhdiFile.files = {}
    monkeypatch.setattr(vhd.pyvhdi, 'file', FakeVhdiFile)
    yield FakeVhdiFile.files
    FakeVhdiFile.files = {}


def _make(
    path: Path,
    registry: dict,
    *,
    parent_filename=None,
    media_size=0,
    identifier=None,
    parent_identifier=None,
    vhdx=True,
) -> Path:
    path.write_bytes(VHDX_HEADER if vhdx else VHD_HEADER)
    registry[str(path.resolve())] = {
        "parent_filename": parent_filename,
        "identifier": identifier,
        "parent_identifier": parent_identifier,
        "media_size": media_size,
    }
    return path


def test_base_only(tmp_path: Path, fake_vhdi):
    base = _make(tmp_path / 'base.vhdx', fake_vhdi, media_size=4096)
    chain = open_vhdx_chain(base)

    assert len(chain.handles) == 1
    assert chain.handle.get_media_size() == 4096


def test_base_plus_child(tmp_path: Path, fake_vhdi):
    _make(
        tmp_path / 'base.vhdx', fake_vhdi,
        media_size=4096, identifier='base-id',
    )
    child = _make(
        tmp_path / 'base-000001.avhdx', fake_vhdi,
        parent_filename='base.vhdx',
        media_size=4096, identifier='child-id', parent_identifier='base-id',
    )
    chain = open_vhdx_chain(child)

    assert len(chain.handles) == 2
    assert chain.handle.get_media_size() == 4096
    # The child must actually be linked to the parent handle so that
    # unallocated blocks fall back to it.
    assert chain.handle._parent is chain.handles[1]


def test_base_plus_two_levels(tmp_path: Path, fake_vhdi):
    _make(
        tmp_path / 'base.vhdx', fake_vhdi,
        media_size=4096, identifier='base-id',
    )
    _make(
        tmp_path / 'base-000001.avhdx', fake_vhdi,
        parent_filename='base.vhdx',
        media_size=4096, identifier='c1-id', parent_identifier='base-id',
    )
    c2 = _make(
        tmp_path / 'base-000002.avhdx', fake_vhdi,
        parent_filename='base-000001.avhdx',
        media_size=4096, identifier='c2-id', parent_identifier='c1-id',
    )
    chain = open_vhdx_chain(c2)

    assert len(chain.handles) == 3
    assert chain.handle._parent is chain.handles[1]
    assert chain.handles[1]._parent is chain.handles[2]


def test_missing_parent_raises(tmp_path: Path, fake_vhdi):
    child = _make(
        tmp_path / 'base-000001.avhdx', fake_vhdi,
        parent_filename='missing.vhdx',
        media_size=4096, identifier='child-id', parent_identifier='base-id',
    )

    with pytest.raises(
        NtfsDumpError, match="Parent AVHDX was not found: missing.vhdx"
    ):
        open_vhdx_chain(child)


def test_circular_parent_raises(tmp_path: Path, fake_vhdi):
    _make(
        tmp_path / 'a.avhdx', fake_vhdi,
        parent_filename='b.avhdx',
        media_size=4096, identifier='a-id', parent_identifier='b-id',
    )
    _make(
        tmp_path / 'b.avhdx', fake_vhdi,
        parent_filename='a.avhdx',
        media_size=4096, identifier='b-id', parent_identifier='a-id',
    )

    with pytest.raises(
        NtfsDumpError, match="Circular VHDX parent reference detected"
    ):
        open_vhdx_chain(tmp_path / 'a.avhdx')


def test_windows_absolute_parent(tmp_path: Path, fake_vhdi):
    _make(
        tmp_path / 'base.vhdx', fake_vhdi,
        media_size=8192, identifier='base-id',
    )
    child = _make(
        tmp_path / 'vm.avhdx', fake_vhdi,
        parent_filename='C:\\VMs\\Base\\base.vhdx',
        media_size=8192, identifier='child-id', parent_identifier='base-id',
    )
    chain = open_vhdx_chain(child)

    assert len(chain.handles) == 2


def test_relative_parent_path_with_parent_directory(tmp_path: Path, fake_vhdi):
    (tmp_path / 'base').mkdir()
    _make(
        tmp_path / 'base' / 'base.vhdx', fake_vhdi,
        media_size=4096, identifier='base-id',
    )
    (tmp_path / 'child').mkdir()
    child = _make(
        tmp_path / 'child' / 'vm.avhdx', fake_vhdi,
        parent_filename='../base/base.vhdx',
        media_size=4096, identifier='child-id', parent_identifier='base-id',
    )
    chain = open_vhdx_chain(child)

    assert len(chain.handles) == 2
    assert chain.handle._parent is chain.handles[1]


def test_parent_identifier_mismatch_raises(tmp_path: Path, fake_vhdi):
    _make(
        tmp_path / 'base.vhdx', fake_vhdi,
        media_size=4096, identifier='base-id',
    )
    child = _make(
        tmp_path / 'vm.avhdx', fake_vhdi,
        parent_filename='base.vhdx',
        media_size=4096, identifier='child-id', parent_identifier='wrong-id',
    )

    with pytest.raises(
        NtfsDumpError, match="Unable to attach parent AVHDX: base.vhdx"
    ):
        open_vhdx_chain(child)


def test_non_vhdx_missing_parent_message(tmp_path: Path, fake_vhdi):
    child = _make(
        tmp_path / 'legacy.vhd', fake_vhdi,
        parent_filename='missing.vhd',
        media_size=4096, identifier='child-id', parent_identifier='base-id',
        vhdx=False,
    )

    with pytest.raises(
        NtfsDumpError, match="Parent VHD was not found: missing.vhd"
    ):
        open_vhdx_chain(child)


def test_vhd_handler_reads_logical_disk(tmp_path: Path, fake_vhdi):
    base = _make(tmp_path / 'base.vhdx', fake_vhdi, media_size=4096)

    img_info = VHDHandler().get_img_info(str(base))

    assert img_info.get_size() == 4096
    assert img_info.read(0, 4) == b'\x00\x00\x00\x00'
    img_info.close()
