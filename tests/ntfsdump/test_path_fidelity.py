"""Internal NTFS paths must survive pipe input and host path conversion."""

import io
from pathlib import PureWindowsPath
from types import SimpleNamespace

import pytest

from ntfsdump import cli
from ntfsdump import volume as volume_module
from ntfsdump.volume import NtfsVolume
from test_directory_ads_real import STREAM_DATA, create_directory_ads_image


@pytest.mark.parametrize("ending", ["\n", "\r\n"])
def test_pipe_paths_preserve_filename_whitespace(monkeypatch, ending):
    paths = ["/folder/file ", "/folder/file\t", "/file:stream "]
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(ending.join(paths) + ending))
    assert cli._collect_paths(SimpleNamespace(paths=[])) == paths


def test_pipe_unterminated_path_preserves_whitespace(monkeypatch):
    path = "/file:stream \t"
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(path))
    assert cli._collect_paths(SimpleNamespace(paths=[])) == [path]


def test_pipe_blank_lines_do_not_remove_whitespace_paths(monkeypatch):
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("\n\r\n \t\n"))
    assert cli._collect_paths(SimpleNamespace(paths=[])) == [" \t"]


def test_native_directory_ads_with_trailing_space_from_pipe(
    prepare_ntfsfile, tmp_path_factory, tmp_path, monkeypatch
):
    image, _ = create_directory_ads_image(prepare_ntfsfile, tmp_path_factory, "trail ")
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO("/test_dir:trail \n"))
    output = tmp_path / "stream.bin"
    assert cli.main([str(image), "--quiet", "--output-file", "-o", str(output)]) == 0
    assert output.read_bytes() == STREAM_DATA


@pytest.mark.parametrize(
    "query, expected",
    [
        ("/C:review", "C_review"),
        ("/D:review", "D_review"),
        ("/C/file:review", "C/file_review"),
        ("/$Extend/$UsnJrnl:review", "$Extend/$UsnJrnl_review"),
    ],
)
@pytest.mark.parametrize("flat", [False, True])
def test_windows_ads_paths_stay_inside_output(monkeypatch, query, expected, flat):
    # Exercise the production target selection with Windows path semantics;
    # only filesystem operations are intercepted so this also runs on Linux.
    monkeypatch.setattr(volume_module, "Path", PureWindowsPath)
    destination = PureWindowsPath("D:/out")
    stream = SimpleNamespace(
        info=SimpleNamespace(name=b"review", size=4, type=128, id=1)
    )

    class File:
        info = SimpleNamespace(meta=SimpleNamespace(addr=42, size=0))

        def __iter__(self):
            return iter([stream])

    volume = NtfsVolume(None, 0, "NTFS", 0, 0, None)
    outputs = []

    def check_target(root, target):
        assert target.is_relative_to(root)
        return target

    monkeypatch.setattr(volume, "_NtfsVolume__check_output_path", check_target)
    monkeypatch.setattr(
        volume, "_NtfsVolume__resolve_collision", lambda target, _: target
    )
    monkeypatch.setattr(
        volume,
        "_NtfsVolume__write_stream",
        lambda file, target, size, attribute: outputs.append((target, size, attribute)),
    )
    # For tree output, is_dir is used only to decide whether collision handling
    # is needed. Avoid consulting the host filesystem for this simulated path.
    monkeypatch.setattr(PureWindowsPath, "is_dir", lambda _: False, raising=False)
    volume._NtfsVolume__dump_file(File(), query, destination, flat, False)
    name = expected.replace("/", "_") if flat else expected
    assert outputs == [(destination / name, 4, stream)]
