# coding: utf-8
from typing import Literal, Optional

from ntfsdump.presenters.NtfsDumpPresenter import NtfsDumpPresenter


def ntfsdump(
    imagefile_path: str,
    output_path: str,
    target_queries: list[str],
    volume_num: Optional[int] = None,
    file_type: Literal[
        'raw',
        'RAW',
        'e01',
        'E01',
        'vhd',
        'VHD',
        'vhdx',
        'VHDX',
        'vmdk',
        'VMDK',
    ] = 'raw'
):
    """A tool for extract any files from an NTFS volume on an image file.

    Args:
        imagefile_path (str): target image file path.
        output_path (str): output target file path, or output target directory path.
        target_queries (list[str]): query for extracted file paths.
        volume_num (Optional[int], optional): system volume number. Defaults to None.
        file_type (Literal['raw', 'e01', 'vhd', 'vhdx', 'vmdk'], optional): target image file format. Defaults to 'raw'.
    """
    NtfsDumpPresenter().ntfsdump(
        imagefile_path,
        output_path,
        target_queries,
        volume_num,
        file_type,
    )