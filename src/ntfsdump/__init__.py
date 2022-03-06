# coding: utf-8
from typing import List, Literal, Optional

from ntfsdump.presenters.NtfsDumpPresenter import NtfsDumpPresenter

def ntfsdump(imagefile_path: str, output_path: str, target_queries: List[str], volume_num: Optional[int] = None, file_type: Literal['raw', 'e01'] = 'raw'):

    NtfsDumpPresenter().ntfsdump(
        imagefile_path=imagefile_path,
        output_path=output_path,
        target_queries=target_queries,
        volume_num=volume_num,
        file_type=file_type,
    )