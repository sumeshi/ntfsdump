# coding: utf-8
"""Regression tests for Windows OS volume auto-selection (ImageFile).

The auto-selection must inspect the filesystem directory tree of every NTFS
candidate instead of blindly picking the last volume, so that multi-volume
layouts (EFI + OS + WinRE + data) select the volume that actually hosts the
Windows directory structure.
"""
from types import SimpleNamespace
from pathlib import Path

import pytsk3
import pytest

from ntfsdump.errors import NtfsDumpError
from ntfsdump.image import ImageFile
from ntfsdump.volume import NtfsVolume


def _fake_entry(name_type: int):
    """Duck-typed result of fs_info.open(): f.info.name.type is all that
    ImageFile.__os_volume_markers inspects."""
    return SimpleNamespace(
        info=SimpleNamespace(name=SimpleNamespace(type=name_type))
    )


class FakeFSInfo:
    """Duck-typed pytsk3.FS_Info driven by a {path: name_type} layout.

    Paths missing from the layout raise, mirroring pytsk3's behaviour for
    non-existing entries.
    """

    def __init__(self, layout: dict):
        self.layout = layout

    def open(self, path: str):
        name_type = self.layout.get(path)
        if name_type is None:
            raise FileNotFoundError(f"No such entry: {path}")
        return _fake_entry(name_type)


def make_fs_info(dirs: list) -> FakeFSInfo:
    """Fake FS where exactly the given top-level paths are directories."""
    return FakeFSInfo({path: pytsk3.TSK_FS_NAME_TYPE_DIR for path in dirs})


def make_volume(tmp_path: Path, addr: int, description: str, fs_info) -> NtfsVolume:
    return NtfsVolume(
        path=tmp_path,
        addr=addr,
        description=description,
        start_byte=0,
        end_byte=0,
        fs_info=fs_info,
    )


def make_image(tmp_path: Path, volumes: list) -> ImageFile:
    # SourceResolver (real image parsing) is bypassed: only the private
    # selection logic is under test.
    image = ImageFile.__new__(ImageFile)
    image.volumes = volumes
    return image


def test_single_os_volume_among_winre_and_data(tmp_path):
    # Windows 10/11 style layout: the OS volume sits in the middle and is
    # neither the first nor the last NTFS volume.
    winre = make_volume(
        tmp_path, 1, 'Windows Recovery Environment',
        make_fs_info(['/Recovery']),
    )
    os_volume = make_volume(
        tmp_path, 2, 'NTFS / exFAT (0x07)',
        make_fs_info(['/Windows', '/Program Files', '/Program Files (x86)', '/Users']),
    )
    data = make_volume(
        tmp_path, 3, 'Basic data partition',
        make_fs_info(['/Data']),
    )

    image = make_image(tmp_path, [winre, os_volume, data])
    result = image._ImageFile__auto_detect_main_partition(None)

    # addr 2 = the OS volume in the middle; the old implementation would
    # have returned the last volume (addr 3).
    assert result.addr == 2


def test_multiple_os_looking_volumes_raises(tmp_path):
    os_v1 = make_volume(
        tmp_path, 1, 'Basic data partition',
        make_fs_info(['/Windows', '/Program Files', '/Users']),
    )
    os_v3 = make_volume(
        tmp_path, 3, 'Windows Recovery Environment',
        make_fs_info(['/Windows', '/ProgramData', '/Users']),
    )

    image = make_image(tmp_path, [os_v1, os_v3])

    with pytest.raises(NtfsDumpError) as excinfo:
        image._ImageFile__auto_detect_main_partition(None)

    message = str(excinfo.value)
    assert 'Multiple NTFS volumes look like Windows OS volumes' in message
    assert '--volume' in message


def test_zero_os_looking_volumes_raises(tmp_path):
    winre = make_volume(
        tmp_path, 1, 'Windows Recovery Environment',
        make_fs_info(['/Recovery']),
    )
    data = make_volume(
        tmp_path, 2, 'Basic data partition',
        make_fs_info(['/Data']),
    )

    image = make_image(tmp_path, [winre, data])

    with pytest.raises(NtfsDumpError) as excinfo:
        image._ImageFile__auto_detect_main_partition(None)

    message = str(excinfo.value)
    assert (
        'Multiple NTFS volumes were found, but none of them looks like a Windows OS volume'
        in message
    )
    assert '--volume' in message


def test_explicit_volume_beats_os_detection(tmp_path):
    os_volume = make_volume(
        tmp_path, 1, 'Basic data partition',
        make_fs_info(['/Windows', '/Program Files', '/Users']),
    )
    winre = make_volume(
        tmp_path, 2, 'Windows Recovery Environment',
        make_fs_info(['/Recovery']),
    )

    image = make_image(tmp_path, [os_volume, winre])
    result = image._ImageFile__auto_detect_main_partition(2)

    # An explicit --volume must win over the OS auto-detection.
    assert result.addr == 2


def test_explicit_volume_not_found_raises(tmp_path):
    os_volume = make_volume(
        tmp_path, 1, 'Basic data partition',
        make_fs_info(['/Windows', '/Program Files']),
    )

    image = make_image(tmp_path, [os_volume])

    with pytest.raises(NtfsDumpError) as excinfo:
        image._ImageFile__auto_detect_main_partition(99)

    assert 'NTFS volume 99 was not found' in str(excinfo.value)


@pytest.mark.parametrize('volume_num, selected_addr', [(None, 27), (5, 5)])
def test_analysis_logs_use_partition_addresses(tmp_path, monkeypatch, capsys, volume_num, selected_addr):
    volumes = [
        make_volume(tmp_path, 5, 'NTFS data', make_fs_info(['/Data'])),
        make_volume(tmp_path, 27, 'NTFS OS', make_fs_info(['/Windows', '/Users'])),
    ]
    source = SimpleNamespace(get_img_info=lambda: object())
    monkeypatch.setattr('ntfsdump.image.SourceResolver.resolve', lambda *args, **kwargs: source)
    monkeypatch.setattr(ImageFile, '_ImageFile__analyze_partitions', lambda self: volumes)

    image = ImageFile(tmp_path, volume=volume_num)

    assert image.main_volume.addr == selected_addr
    output = capsys.readouterr().out
    assert 'NTFS Volume 5: NTFS data' in output
    assert 'NTFS Volume 27: NTFS OS' in output
    assert f'Volume {selected_addr} was selected as the main partition' in output
    assert 'NTFS Volume 0:' not in output
    assert 'NTFS Volume 1:' not in output


def test_data_volume_with_windows_dir_only_is_not_os_candidate(tmp_path):
    # A data volume that happens to carry a bare '/Windows' directory has
    # only one OS marker; without a second indicator it must not be treated
    # as an OS volume.
    fake_os = make_volume(
        tmp_path, 1, 'Basic data partition',
        make_fs_info(['/Windows']),
    )
    data = make_volume(
        tmp_path, 2, 'Basic data partition',
        make_fs_info(['/Data']),
    )

    image = make_image(tmp_path, [fake_os, data])

    with pytest.raises(NtfsDumpError) as excinfo:
        image._ImageFile__auto_detect_main_partition(None)

    # Zero candidates: had volume 1 been recognized as the OS volume it
    # would have been auto-selected here instead.
    assert (
        'none of them looks like a Windows OS volume' in str(excinfo.value)
    )
