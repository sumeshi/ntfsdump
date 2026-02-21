# coding: utf-8
from hashlib import md5
from pathlib import Path

import pytest
from ntfsdump import ntfsdump


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
def test_ntfsdump(query: str, hash_list: set[str]):
    # extraction via python-module
    cachedir = Path(__file__).parent / 'cache'

    ntfsdump(
        image=cachedir / 'ntfs.raw',
        paths=[query],
        output=cachedir,
    )
    created_files = cachedir.glob('**/*[!raw]')
    cache_hash_list = {calc_md5(f) for f in created_files}
    assert hash_list <= cache_hash_list
