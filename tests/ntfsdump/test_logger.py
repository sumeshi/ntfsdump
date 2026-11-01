import json
from pathlib import Path

import pytest

from ntfsdump.cli import main
from ntfsdump.errors import NtfsDumpError
from ntfsdump.logger import configure_logging, get_logger, protect_source_paths


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
def test_cli_log_cannot_modify_source_or_alias(tmp_path, alias, capsys):
    source = tmp_path / "image.raw"
    original = b"\x00" * 1024
    source.write_bytes(original)
    log = source
    if alias != "same":
        log = tmp_path / "log.txt"
        if alias == "symlink":
            log.symlink_to(source)
        else:
            log.hardlink_to(source)

    assert main([str(source), "/$MFT", "--log", str(log)]) == 1
    assert "overwrite an input image" in capsys.readouterr().err
    assert source.read_bytes() == original
    assert log.read_bytes() == original


@pytest.mark.parametrize("redirect_on_open", [1, 2])
def test_log_checks_opened_file_identity_before_any_write(
    tmp_path,
    monkeypatch,
    redirect_on_open,
):
    source = tmp_path / "image.raw"
    source.write_bytes(b"evidence")
    log = tmp_path / "log.txt"
    configure_logging(str(log))
    protect_source_paths([source])
    original_open = Path.open
    opens = 0

    def redirected_open(path, mode="r", *args, **kwargs):
        nonlocal opens
        if path == log and mode == "a":
            opens += 1
            if opens == redirect_on_open:
                # Simulate the destination changing during open and then
                # changing back before the path-based validation runs.
                return original_open(source, mode, *args, **kwargs)
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", redirected_open)
    with pytest.raises(NtfsDumpError, match="overwrite an input image"):
        get_logger().log("must not be written to evidence")
    assert source.read_bytes() == b"evidence"


def test_existing_unrelated_log_is_appended(tmp_path):
    source = tmp_path / "image.raw"
    source.write_bytes(b"evidence")
    log = tmp_path / "log.txt"
    log.write_text("previous run\n")
    configure_logging(str(log))
    protect_source_paths([source])

    get_logger().log("current run")

    assert log.read_text().startswith("previous run\n")
    assert "current run" in log.read_text()
    assert source.read_bytes() == b"evidence"


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
def test_cli_log_cannot_modify_extracted_file_or_alias(tmp_path, alias):
    fixture = json.loads(Path("/workspace/.review-fixtures/manifest.json").read_text())
    output = tmp_path / "stream.bin"
    output.write_bytes(b"preserve this")
    log = output
    if alias != "same":
        log = tmp_path / "log.txt"
        if alias == "symlink":
            log.symlink_to(output)
        else:
            log.hardlink_to(output)

    assert (
        main(
            [
                fixture["directory_ads"],
                "/test_dir:review",
                "--quiet",
                "--output-file",
                "-o",
                str(output),
                "--log",
                str(log),
            ]
        )
        == 1
    )
    assert output.read_bytes() == b"preserve this"


def test_cli_failure_is_appended_to_enabled_log(tmp_path, capsys):
    fixture = json.loads(Path("/workspace/.review-fixtures/manifest.json").read_text())
    log = tmp_path / "case.log"

    assert (
        main([fixture["directory_ads"], "/missing-path", "--quiet", "--log", str(log)])
        == 1
    )

    captured = capsys.readouterr()
    assert "Query path was not found" in captured.err
    contents = log.read_text()
    assert "[query] /missing-path" in contents
    assert "[error] Query path was not found" in contents
