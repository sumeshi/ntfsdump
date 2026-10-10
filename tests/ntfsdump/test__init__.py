# coding: utf-8
from hashlib import md5
from pathlib import Path

import pytest
from ntfsdump import ntfsdump
from ntfsdump.errors import NtfsDumpError


def calc_md5(path: Path) -> str:
    if path.is_dir():
        return ''
    else:
        return md5(path.read_bytes()).hexdigest()


@pytest.mark.parametrize('query, hash_list', [
    ('/$MFT', {'edb7605e808ec25c8e5feea382a49047'}),
    ('/$Extend/$UsnJrnl:$J', {'7385c81db5803d8d6dc19cfdf07bde81'}),
    ('/$Extend/$RmMetadata/$Txflog', {
        '892fce8a91fca1c6701d3b4720f82b0d',
        '251144a40647b94efd0aabbb9d8f227f',
        'c2814e14d7c78636e9ddea496efd43f1',
        'f1c9645dbc14efddc7d8a322685f26eb'
    }),
])
def test_ntfsdump(query: str, hash_list: set[str], prepare_ntfsfile, tmp_path):
    # extraction via python-module
    ntfsdump(
        source=prepare_ntfsfile,
        paths=[query],
        output=tmp_path,
    )
    created_files = tmp_path.rglob('*')
    cache_hash_list = {calc_md5(f) for f in created_files}
    assert hash_list <= cache_hash_list


def test_missing_query_is_reported_as_not_found(prepare_ntfsfile, tmp_path):
    with pytest.raises(NtfsDumpError, match='Query path was not found'):
        ntfsdump(
            source=prepare_ntfsfile,
            paths=['/ntfsdump-missing-file-for-regression-test'],
            output=tmp_path,
        )
    assert not list(tmp_path.iterdir())


def test_ntfsdump_creates_renamed_output_file(prepare_ntfsfile, tmp_path):
    output = tmp_path / 'renamed-mft.bin'
    ntfsdump(source=prepare_ntfsfile, paths=['/$MFT'], output=output, output_file=True)

    assert calc_md5(output) == 'edb7605e808ec25c8e5feea382a49047'
    assert list(tmp_path.iterdir()) == [output]
