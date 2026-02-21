# coding: utf-8
from pathlib import Path
from typing import List, Literal, Optional

import pytsk3

from ntfsdump.volume import NtfsVolume
from ntfsdump.logger import get_logger
from ntfsdump.formats import get_format_handler


logger = get_logger()


class ImageFile:
    def __init__(
        self,
        path: Path,
        volume_num: Optional[int],
        file_type: Literal[
            'raw', 'RAW', 'e01', 'E01', 'vhd', 'VHD',
            'vhdx', 'VHDX', 'vmdk', 'VMDK'
        ] = 'raw'
    ):
        self.path = path
        self.block_size = 512
        self.file_type = file_type.lower()
        self.volumes = self.__analyze_partitions()
        self.main_volume = self.__auto_detect_main_partition(volume_num)

        logger.log(f"[analyze] {len(self.volumes)} volumes were detected as NTFS volumes.", 'system')
        for index, volume in enumerate(self.volumes):
            logger.log(f"[analyze] NTFS Volume {index}: {volume.description}", 'system')
        logger.log(f"[analyze] Volume {self.volumes.index(self.main_volume)} was automatically detected as the main partition.", 'system')

    def __analyze_partitions(self) -> List[NtfsVolume]:
        logger.log(f"[analyze] {self.file_type.upper()} Format Image", 'system')
        handler = get_format_handler(self.file_type)
        img_info = handler.get_img_info(str(self.path))

        volumes = pytsk3.Volume_Info(img_info)
        self.block_size = volumes.info.block_size

        return [
            NtfsVolume(
                path=self.path,
                addr=volume.addr,
                description=volume.desc.decode('utf-8'),
                start_byte=volume.start,
                end_byte=volume.start + volume.len - 1,
                fs_info=pytsk3.FS_Info(img_info, self.block_size * volume.start, pytsk3.TSK_FS_TYPE_NTFS)
            ) for volume in volumes if volume.desc.decode('utf-8').startswith('NTFS')
        ]
    
    def __auto_detect_main_partition(self, volume_num: Optional[int]) -> NtfsVolume:
        if volume_num is not None:
            # user specify addr
            return next(v for v in self.volumes if v.addr == volume_num)
        elif len(self.volumes) == 1:
            # windows xp ~ vista
            return self.volumes[0]
        else:
            # windows 7 ~ or generalized: bacause first ntfs partition is usually recovery
            return self.volumes[-1]
