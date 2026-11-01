# coding: utf-8
from pathlib import Path
from typing import Optional, Union

from ntfsdump.image import ImageFile
from ntfsdump.image_paths import ensure_distinct_output
from ntfsdump.logger import MetaData, get_logger
from ntfsdump.errors import NtfsDumpError


def ntfsdump(
    source: Union[str, Path],
    paths: list[str],
    output: Union[str, Path] = ".",
    volume: Optional[int] = None,
    image_format: Optional[str] = None,
    snapshot=None,
    disk: Optional[int] = None,
    flat: bool = False,
    quiet: bool = False,
    output_file: bool = False,
) -> None:
    """A tool for extracting files from an NTFS volume on a disk image.

    Args:
        source (Union[str, Path]): disk image file, VMware VM directory, VMX or VMSD.
        paths (list[str]): query paths to extract.
        output (Union[str, Path], optional): output directory or file path.
            Defaults to ".".
        volume (Optional[int], optional): target NTFS volume number. Defaults to None.
        image_format (Optional[str], optional): force the image format
            ('raw', 'e01', 'vhd', 'vhdx', 'vmdk'). Defaults to None (auto-detect).
        snapshot (optional): VMware snapshot ID to read. Defaults to None.
        disk (Optional[int], optional): VMware virtual disk ID to read.
            Defaults to None.
        flat (bool, optional): reconstruct directory tree or not. Defaults to False.
        quiet (bool, optional): suppress progress lines on stdout.
            Errors are still written to stderr. Defaults to False.
        output_file (bool, optional): treat output as a file path.
            Requires one file or ADS query.
    """
    MetaData.quiet = quiet
    output_path = Path(output).absolute()
    # An explicit file destination is known before opening the image. Reject a
    # log alias here so even image/volume setup failures cannot append to it.
    if output_file or output_path.is_file():
        get_logger().ensure_not_output(output_path)
    if (output_file or output_path.is_file()) and len(paths) != 1:
        raise NtfsDumpError("File output requires a single file or ADS query.")
    img = ImageFile(
        source,
        volume=volume,
        image_format=image_format,
        snapshot=snapshot,
        disk=disk,
    )
    ensure_distinct_output(output_path, img.source_paths)
    for query in paths:
        img.main_volume.dump_files(query, output_path, flat, output_file=output_file)
