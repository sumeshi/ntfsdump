# coding: utf-8
import pytest

from ntfsdump import core
from ntfsdump.logger import MetaData
from ntfsdump.errors import NtfsDumpError


def test_ntfsdump_resets_leaked_quiet_state(tmp_path, monkeypatch):
    # A previous ntfsfind(verbose=True) call may leave MetaData.quiet=True
    # in the same process; core.ntfsdump() must reset it explicitly.
    monkeypatch.setattr(MetaData, 'quiet', True)

    with pytest.raises(Exception):
        core.ntfsdump(source=str(tmp_path), paths=['/$MFT'])

    assert MetaData.quiet is False


def test_ntfsdump_quiet_flag_is_applied(tmp_path, monkeypatch):
    monkeypatch.setattr(MetaData, 'quiet', False)

    with pytest.raises(Exception):
        core.ntfsdump(source=str(tmp_path), paths=['/$MFT'], quiet=True)

    assert MetaData.quiet is True


def test_cli_passes_quiet_to_core(monkeypatch):
    from ntfsdump import cli

    captured = {}

    def fake_ntfsdump(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(cli, 'ntfsdump', fake_ntfsdump)
    monkeypatch.setattr(
        cli.SourceResolver,
        'resolve',
        lambda self, source, **kwargs: object(),
    )

    cli.main([str('/nonexistent'), '/$MFT', '--quiet'])

    assert captured['quiet'] is True


@pytest.mark.parametrize('explicit', [False, True])
def test_file_output_rejects_multiple_queries_before_opening_image(tmp_path, explicit):
    output = tmp_path / 'out.bin'
    output.write_bytes(b'existing evidence')

    with pytest.raises(NtfsDumpError, match='File output requires a single file or ADS query'):
        core.ntfsdump(
            source='/nonexistent', paths=['/one.bin', '/two.bin'],
            output=output, output_file=explicit,
        )
    assert output.read_bytes() == b'existing evidence'


def test_cli_passes_output_file_to_core(monkeypatch):
    from ntfsdump import cli

    captured = {}
    monkeypatch.setattr(cli, 'ntfsdump', lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(cli.SourceResolver, 'resolve', lambda *args, **kwargs: object())

    assert cli.main(['/nonexistent', '/file.bin', '--output-file', '-o', 'renamed.bin']) == 0
    assert captured['output_file'] is True
    assert captured['output'] == 'renamed.bin'
