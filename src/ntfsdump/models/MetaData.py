# coding: utf-8
from typing import Optional, Final
from datetime import datetime
from importlib.metadata import version, PackageNotFoundError


def get_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return ''


class MetaData(object):
    name: Final[str] = 'ntfsdump'
    version: Final[str] = get_version(name)
    run_time: Optional[datetime] = None
    quiet: bool = True
    nolog: bool = True
