# coding: utf-8
from pathlib import Path

import pytest

from ntfsdump.cli import create_parser, main
from ntfsdump.logger import AUTO_LOG, MetaData, configure_logging, get_logger

FIXTURES = Path(__file__).parent / 'fixtures' / 'vmware'
WINDOWS_VM = FIXTURES / 'WindowsVM'


def test_parser_accepts_new_cli():
    args = create_parser().parse_args(
        ['Windows.vmdk', '/$MFT', '-s', '3', '-d', '1', '--image-format', 'vmdk']
    )

    assert args.source == 'Windows.vmdk'
    assert args.paths == ['/$MFT']
    assert args.snapshot == '3'
    assert args.disk == 1
    assert args.image_format == 'vmdk'


def test_parser_log_optional_value():
    parser = create_parser()

    assert parser.parse_args(['evidence.raw', '/$MFT']).log is None
    assert parser.parse_args(['evidence.raw', '/$MFT', '--log']).log == AUTO_LOG
    assert parser.parse_args(
        ['evidence.raw', '/$MFT', '--log', './case.log']
    ).log == './case.log'


def test_parser_rejects_removed_options():
    parser = create_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(['--no-log', 'evidence.raw', '/$MFT'])
    with pytest.raises(SystemExit):
        parser.parse_args(['--format', 'raw', 'evidence.raw', '/$MFT'])


def test_configure_logging_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    configure_logging(None)
    get_logger().log('hello')

    assert list(tmp_path.glob('*.log')) == []


def test_configure_logging_explicit_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    log_path = tmp_path / 'case.log'
    configure_logging(str(log_path))
    get_logger().log('hello')

    assert log_path.exists()
    assert 'hello' in log_path.read_text()


def test_configure_logging_auto_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    configure_logging(AUTO_LOG)
    get_logger().log('hello')

    logs = list(tmp_path.glob('ntfsdump_*.log'))
    assert len(logs) == 1


def test_list_snapshots_output(capsys):
    assert main([str(WINDOWS_VM), '--list-snapshots']) == 0
    out = capsys.readouterr().out

    assert 'ID  NAME' in out
    assert 'Before Windows Update' in out
    assert 'Before Investigation' in out


def test_list_disks_output(capsys):
    assert main([str(WINDOWS_VM), '--list-disks']) == 0
    out = capsys.readouterr().out

    assert 'ID  NODE' in out
    assert 'scsi0:0' in out
    assert 'scsi0:1' in out


def test_list_snapshots_on_non_vmware_errors(capsys, tmp_path):
    raw = tmp_path / 'evidence.raw'
    raw.write_bytes(b'\x00' * 8192)

    assert main([str(raw), '--list-snapshots']) == 1
    err = capsys.readouterr().err
    assert 'No VMware snapshot metadata was found.' in err


def test_errors_are_shown_even_with_quiet(capsys):
    assert main([str(WINDOWS_VM), '-q', '-s', '42', '/Evidence']) == 1
    err = capsys.readouterr().err
    assert 'Snapshot ID 42 was not found.' in err


def test_missing_source_errors(capsys):
    assert main(['/nonexistent/evidence.raw', '/$MFT']) == 1
    err = capsys.readouterr().err
    assert 'No such file or directory' in err


def test_non_vm_directory_errors(capsys, tmp_path):
    empty = tmp_path / 'NotAVM'
    empty.mkdir()

    assert main([str(empty), '/$MFT']) == 1
    err = capsys.readouterr().err
    assert 'No VMware VM files' in err
    assert str(empty) in err


def test_unexpected_error_traceback_with_debug_env(capsys, monkeypatch, tmp_path):
    import ntfsdump.cli as cli_mod

    def raise_runtime_error(*args, **kwargs):
        raise RuntimeError('unexpected backend failure')

    monkeypatch.setattr(cli_mod, '_run', raise_runtime_error)
    monkeypatch.setenv('NTFSDUMP_DEBUG', '1')

    assert main([str(tmp_path), '/$MFT']) == 1
    captured = capsys.readouterr()
    assert 'unexpected backend failure' in captured.err
    assert 'Traceback' in captured.err


def test_unexpected_error_hides_traceback_by_default(capsys, monkeypatch, tmp_path):
    import ntfsdump.cli as cli_mod

    def raise_runtime_error(*args, **kwargs):
        raise RuntimeError('unexpected backend failure')

    monkeypatch.setattr(cli_mod, '_run', raise_runtime_error)
    monkeypatch.delenv('NTFSDUMP_DEBUG', raising=False)

    assert main([str(tmp_path), '/$MFT']) == 1
    err = capsys.readouterr().err
    assert 'unexpected backend failure' in err
    assert 'Traceback' not in err


def test_vmsd_source_is_resolved(capsys):
    assert main([str(WINDOWS_VM / 'WindowsVM.vmsd'), '--list-snapshots']) == 0
    out = capsys.readouterr().out
    assert 'Before Investigation' in out


@pytest.fixture(autouse=True)
def _reset_metadata():
    yield
    MetaData.quiet = False
    configure_logging(None)
