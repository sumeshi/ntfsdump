# coding: utf-8
from pathlib import Path
from typing import Optional, Union

from ntfsdump.image import ImageFile


def ntfsdump(
    source: Union[str, Path],
    paths: list[str],
    output: Union[str, Path] = ".",
    volume: Optional[int] = None,
    image_format: Optional[str] = None,
    snapshot=None,
    disk: Optional[int] = None,
    flat: bool = False,
) -> None:
    """A tool for extracting files from an NTFS volume on a disk image.

    Args:
        source (Union[str, Path]): disk image file, VMware VM directory, VMX or VMSD.
        paths (list[str]): query paths to extract.
        output (Union[str, Path], optional): output destination directory or file path. Defaults to ".".
        volume (Optional[int], optional): target NTFS volume number. Defaults to None.
        image_format (Optional[str], optional): force the image format
            ('raw', 'e01', 'vhd', 'vhdx', 'vmdk'). Defaults to None (auto-detect).
        snapshot (optional): VMware snapshot ID to read. Defaults to None.
        disk (Optional[int], optional): VMware virtual disk ID to read. Defaults to None.
        flat (bool, optional): reconstruct directory tree or not. Defaults to False.
    """
    img = ImageFile(
        source,
        volume=volume,
        image_format=image_format,
        snapshot=snapshot,
        disk=disk,
    )
    output_dir = Path(output).resolve()

    for query in paths:
        img.main_volume.dump_files(query, output_dir, flat)
