# coding: utf-8
from pathlib import Path

import pytest

from ntfsdump.errors import NtfsDumpError
from ntfsdump.formats import get_format_handler
from ntfsdump.formats.detect import detect_image_format, is_vhdx_file


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def test_detect_raw(tmp_path: Path):
    image = _write(tmp_path / 'evidence.raw', b'\x00' * 8192)
    assert detect_image_format(image) == 'raw'


def test_detect_e01(tmp_path: Path):
    image = _write(tmp_path / 'evidence.E01', b'EVF\x09\x0d\x0a\xff\x00' + b'\x00' * 8192)
    assert detect_image_format(image) == 'e01'


def test_detect_vhd(tmp_path: Path):
    image = _write(
        tmp_path / 'disk.vhd',
        b'\x00' * 7600 + b'conectix' + b'\x00' * (512 - 8),
    )
    assert detect_image_format(image) == 'vhd'


def test_detect_vhdx(tmp_path: Path):
    image = _write(tmp_path / 'disk.vhdx', b'vhdxfile' + b'\x00' * 8192)
    assert detect_image_format(image) == 'vhdx'


def test_detect_vhdx_by_signature_only(tmp_path: Path):
    # Signature wins even without a .vhdx/.avhdx extension.
    image = _write(tmp_path / 'disk.bin', b'vhdxfile' + b'\x00' * 8192)
    assert detect_image_format(image) == 'vhdx'


def test_detect_avhdx_by_extension_only(tmp_path: Path):
    # Extension is accepted when the signature check is inconclusive.
    image = _write(tmp_path / 'Disk_0.avhdx', b'\x00' * 8192)
    assert detect_image_format(image) == 'vhdx'


def test_detect_avhdx(tmp_path: Path):
    image = _write(tmp_path / 'Disk_0.avhdx', b'vhdxfile' + b'\x00' * 8192)
    assert detect_image_format(image) == 'vhdx'
    assert is_vhdx_file(image) is True


def test_is_vhdx_file_false_for_vhd(tmp_path: Path):
    image = _write(tmp_path / 'disk.vhd', b'conectix' + b'\x00' * 512)
    assert is_vhdx_file(image) is False


def test_detect_vmdk_descriptor(tmp_path: Path):
    image = _write(
        tmp_path / 'Windows.vmdk',
        b'# Disk DescriptorFile\nversion=1\nCID=fffffffe\n',
    )
    assert detect_image_format(image) == 'vmdk'


def test_detect_vmdk_sparse(tmp_path: Path):
    image = _write(tmp_path / 'disk.vmdk', b'KDMV' + b'\x00' * 8192)
    assert detect_image_format(image) == 'vmdk'


def test_detect_unknown_falls_back_to_raw(tmp_path: Path):
    image = _write(tmp_path / 'evidence.bin', b'not a known signature' * 100)
    assert detect_image_format(image) == 'raw'


def test_detect_missing_file_raises(tmp_path: Path):
    with pytest.raises(NtfsDumpError):
        detect_image_format(tmp_path / 'missing.raw')


def test_detect_directory_raises(tmp_path: Path):
    with pytest.raises(NtfsDumpError, match="Unable to detect input image format."):
        detect_image_format(tmp_path)


def test_get_format_handler_unknown_raises():
    with pytest.raises(NtfsDumpError, match="Unknown image format"):
        get_format_handler('qcow2')
