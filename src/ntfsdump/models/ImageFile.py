# coding: utf-8
from pathlib import Path
from typing import List, Literal, Optional

from ntfsdump.models.NtfsVolume import NtfsVolume
from ntfsdump.models.Log import Log

import pytsk3
import pyewf
import pyvhdi
import pyvmdk


class Img_Info(pytsk3.Img_Info):
    def __init__(self, handle):
        self.handle = handle
        super(Img_Info, self).__init__(url="", type=pytsk3.TSK_IMG_TYPE_EXTERNAL)

    def close(self):
        self.handle.close()

    def read(self, offset, size):
        self.handle.seek(offset)
        return self.handle.read(size)

    def get_size(self):
        return self.handle.get_media_size()


class ImageFile(object):
    def __init__(
        self,
        path: Path,
        volume_num: Optional[int],
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
        self.path: Path = path
        self.logger: Log = Log()
        self.block_size: int = 512
        self.file_type: Literal[
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
        ] = file_type
        self.volumes: List[NtfsVolume] = self.__analyze_partitions()
        self.main_volume: NtfsVolume = self.__auto_detect_main_partition(volume_num)

        self.logger.log(f"[analyze] {len(self.volumes)} volumes were detected as NTFS volumes.", 'system')
        for index, volume in enumerate(self.volumes):
            self.logger.log(f"[analyze] NTFS Volume {index}: {volume.description}", 'system')
        self.logger.log(f"[analyze] Volume {self.volumes.index(self.main_volume)} was automatically detected as the main partition.", 'system')

    def __analyze_partitions(self) -> List[NtfsVolume]:
        if self.file_type in ['e01', 'E01']:
            self.logger.log(f"[analyze] E01 Format Image", 'system')
            filenames = pyewf.glob(str(self.path))
            ewf_handle = pyewf.handle()
            ewf_handle.open(filenames)
            img_info = Img_Info(ewf_handle)
        elif self.file_type in ['vhd', 'vhdx', 'VHD', 'VHDX']:
            self.logger.log(f"[analyze] VHD Format Image", 'system')
            vhdi_file = pyvhdi.file()
            vhdi_file.open(str(self.path))
            img_info = Img_Info(vhdi_file)
        elif self.file_type in ['vmdk', 'VMDK']:
            self.logger.log(f"[analyze] VMDK Format Image", 'system')
            vmdk_handle = pyvmdk.handle()
            vmdk_handle.open(str(self.path))
            vmdk_handle.open_extent_data_files()
            img_info = Img_Info(vmdk_handle)
        else:
            self.logger.log(f"[analyze] Raw Format Image", 'system')
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