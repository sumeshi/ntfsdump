# coding: utf-8
from pathlib import Path
from typing import List, Literal, Optional

from ntfsdump.models.NtfsVolume import NtfsVolume

import pytsk3
import pyewf

class ewf_Img_Info(pytsk3.Img_Info):
  def __init__(self, ewf_handle):
    self._ewf_handle = ewf_handle
    super(ewf_Img_Info, self).__init__(
        url="", type=pytsk3.TSK_IMG_TYPE_EXTERNAL)

  def close(self):
    self._ewf_handle.close()

  def read(self, offset, size):
    self._ewf_handle.seek(offset)
    return self._ewf_handle.read(size)

  def get_size(self):
    return self._ewf_handle.get_media_size()


class ImageFile(object):
    def __init__(self, path: Path, volume_num: Optional[int], file_type: Literal['raw', 'e01'] = 'raw'):
        self.path: Path = path
        self.block_size: int = 512
        self.file_type: Literal['raw', 'e01'] = file_type
        self.volumes: List[NtfsVolume] = self.__analyze_partitions()
        self.main_volume: NtfsVolume = self.__auto_detect_main_partition(volume_num)

    def __analyze_partitions(self) -> List[NtfsVolume]:
        if self.file_type == 'e01':
            filenames = pyewf.glob(str(self.path))
            ewf_handle = pyewf.handle()
            ewf_handle.open(filenames)
            img_info = ewf_Img_Info(ewf_handle)
        else:
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