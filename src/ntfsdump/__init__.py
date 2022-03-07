# coding: utf-8
from typing import Literal, Optional

from ntfsdump.presenters.NtfsDumpPresenter import NtfsDumpPresenter

def ntfsdump(
    imagefile_path: str,
    output_path: str,
    target_queries: list[str],
    volume_num: Optional[int] = None,
    file_type: Literal['raw', 'e01'] = 'raw'
):

    NtfsDumpPresenter().ntfsdump(
        imagefile_path,
        output_path,
        target_queries,
        volume_num,
        file_type,
    )