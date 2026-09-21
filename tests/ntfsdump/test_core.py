# coding: utf-8
import pytest

from ntfsdump import core
from ntfsdump.logger import MetaData


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
