# coding: utf-8
from pathlib import Path
from typing import List, Optional

from ntfsdump.models.NtfsVolume import NtfsVolume

import pytsk3

class ImageFile(object):
    def __init__(self, path: Path, volume_num: Optional[int]):
        self.path: Path = path
        self.block_size: int = 512
        self.volumes: List[NtfsVolume] = self.__analyze_partitions()
        self.main_volume: NtfsVolume = self.__auto_detect_main_partition(volume_num)

    def __analyze_partitions(self) -> List[NtfsVolume]:
        img_info = pytsk3.Img_Info(str(self.path))
        volumes = pytsk3.Volume_Info(img_info)

        self.block_size = volumes.info.block_size

        return [
            NtfsVolume(
                path=self.path,
                addr=volume.addr,
                description=volume.desc.decode('utf-8'),
                start_byte=volume.start,
                end_byte=volume.start+volume.len-1,
                fs_info=pytsk3.FS_Info(img_info, self.block_size * volume.start, pytsk3.TSK_FS_TYPE_NTFS)
            ) for volume in volumes if volume.desc.decode('utf-8').startswith('NTFS')
        ]
    
    def __auto_detect_main_partition(self, volume_num: Optional[int]) -> NtfsVolume:
        if volume_num:
            # user specify addr
            return [v for v in self.volumes if v.addr == volume_num][0]

        elif len(self.volumes) == 1:
            # windows xp ~ vista
            return self.volumes[0]

        elif len(self.volumes) == 2:
            # windows 7 ~
            # bacause first ntfs partition is recovery partition.
            return self.volumes[-1]

        else:
            return self.volumes[-1]