# config: utf-8
import hashlib
import tarfile
from pathlib import Path
from urllib import request

import pytest


@pytest.fixture(scope='session', autouse=True)
def prepare_ntfsfile():
    # setup
    ## download ntfs sample
    url = 'https://github.com/msuhanov/ntfs-samples/blob/master/ntfs.tgz?raw=true'
    ntfs_tgs = Path(__file__).parent / Path('cache') / ('ntfs.tgs')
    request.urlretrieve(url, ntfs_tgs.resolve())
    ntfs_md5 = hashlib.md5(ntfs_tgs.read_bytes()).hexdigest()
    assert ntfs_md5 == '79b3b6f3fa173fd0d2a05d0d2693afd0'

    ## extract tarfile
    with tarfile.open(ntfs_tgs.resolve(), 'r:gz') as t:
        
        import os
        
        def is_within_directory(directory, target):
            
            abs_directory = os.path.abspath(directory)
            abs_target = os.path.abspath(target)
        
            prefix = os.path.commonprefix([abs_directory, abs_target])
            
            return prefix == abs_directory
        
        def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
        
            for member in tar.getmembers():
                member_path = os.path.join(path, member.name)
                if not is_within_directory(path, member_path):
                    raise Exception("Attempted Path Traversal in Tar File")
        
            tar.extractall(path, members, numeric_owner=numeric_owner) 
            
        
        safe_extract(t, path=ntfs_tgs.parent)


    yield
    # teardown
    ## remove cache files
    # cachedir = Path(__file__).parent / Path('cache')
    # for file in cachedir.glob('**/*[!.gitkeep]'):
    #     file.unlink()