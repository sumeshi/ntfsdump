# coding: utf-8
from typing import Optional, Final
from datetime import datetime
from importlib.metadata import version


class MetaData(object):
    name: Final[str] = 'ntfsdump'
    version: Final[str] = version(name)
    run_time: Optional[datetime] = None
    quiet: bool = False
    nolog: bool = False
