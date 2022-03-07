# coding: utf-8
from typing import Literal, Optional
from importlib.metadata import version

from ntfsdump.presenters.NtfsDumpPresenter import NtfsDumpPresenter


def get_program_name() -> str:
    return 'ntfsdump'

def get_version() -> str:
    return version(get_program_name())


def ntfsdump(
    imagefile_path: str,
    output_path: str,
    target_queries: list[str],
    volume_num: Optional[int] = None,
    file_type: Literal['raw', 'e01'] = 'raw'
):
    """A tool for extract any files from an NTFS volume on an image file.

    Args:
        imagefile_path (str): target image file path.
        output_path (str): output target file path, or output target directory path.
        target_queries (list[str]): query for extracted file paths.
        volume_num (Optional[int], optional): system volume number. Defaults to None.
        file_type (Literal['raw', 'e01'], optional): target image file format. Defaults to 'raw'.
    """
    NtfsDumpPresenter().ntfsdump(
        imagefile_path,
        output_path,
        target_queries,
        volume_num,
        file_type,
    )