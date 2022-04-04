# coding: utf-8
from pathlib import Path
from typing import List, Literal, Optional

from ntfsdump.models.ImageFile import ImageFile

class NtfsDumpPresenter(object):
    def ntfsdump(
        self,
        imagefile_path: str,
        output_path: str,
        target_queries: List[str],
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
        # dump files
        image = ImageFile(Path(imagefile_path), volume_num, file_type)
        for target_query in target_queries:
            image.main_volume.dump_files(
                target_query, Path(output_path).resolve()
            )