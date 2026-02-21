# coding: utf-8
from pathlib import Path
from typing import Literal, Optional, Union

from ntfsdump.image import ImageFile


def ntfsdump(
    image: Union[str, Path],
    paths: list[str],
    output: Union[str, Path] = ".",
    volume: Optional[int] = None,
    format: str = "raw"
) -> None:
    """A tool for extracting files from an NTFS volume on an image file.

    Args:
        image (Union[str, Path]): target image file path.
        paths (list[str]): query paths to extract.
        output (Union[str, Path], optional): output destination directory or file path. Defaults to ".".
        volume (Optional[int], optional): target NTFS volume number. Defaults to None.
        format (str, optional): target image file format ('raw', 'e01', 'vhd', 'vhdx', 'vmdk'). Defaults to 'raw'.
    """
    img = ImageFile(Path(image), volume, format)
    output_dir = Path(output).resolve()
    
    for query in paths:
        img.main_volume.dump_files(query, output_dir)
