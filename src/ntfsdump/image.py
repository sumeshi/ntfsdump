# coding: utf-8
from pathlib import Path
from typing import List, Optional, Union

import pytsk3

from ntfsdump.errors import NtfsDumpError
from ntfsdump.volume import NtfsVolume
from ntfsdump.logger import get_logger
from ntfsdump.sources import SourceResolver


logger = get_logger()


NTFS_VOLUME_DESCRIPTIONS = (
    # MBR: TSK reports NTFS partitions as "NTFS / exFAT (0x07)".
    'NTFS',
    # GPT: TSK labels partitions from their type GUID, not the filesystem.
    # "Basic data partition" (Microsoft basic data) is the usual Windows/NTFS
    # entry; "Windows Recovery Environment" is NTFS as well.
    'Basic data partition',
    'Windows Recovery Environment',
)


def is_ntfs_volume_description(description: str) -> bool:
    """Whether a pytsk3 volume description marks an NTFS partition candidate.

    The description alone is not definitive for GPT disks (a "Basic data
    partition" may be exFAT), so candidates are verified with FS_Info.
    """
    return description.startswith(NTFS_VOLUME_DESCRIPTIONS)


class ImageFile:
    def __init__(
        self,
        source: Union[str, Path],
        volume: Optional[int] = None,
        image_format: Optional[str] = None,
        snapshot=None,
        disk: Optional[int] = None,
    ):
        self.source = source
        self.block_size = 512
        self.resolved = SourceResolver().resolve(
            source,
            image_format=image_format,
            snapshot=snapshot,
            disk=disk,
        )
        self.img_info = self.resolved.get_img_info()
        self.volumes = self.__analyze_partitions()
        self.main_volume = self.__auto_detect_main_partition(volume)

        logger.log(
            f"[analyze] {len(self.volumes)} volumes were detected as NTFS volumes.",
            'system',
        )
        for index, item in enumerate(self.volumes):
            logger.log(f"[analyze] NTFS Volume {index}: {item.description}", 'system')
        logger.log(
            f"[analyze] Volume {self.volumes.index(self.main_volume)} was automatically detected as the main partition.",
            'system',
        )

    def __analyze_partitions(self) -> List[NtfsVolume]:
        logger.log(f"[analyze] {self.resolved.format.upper()} Format Image", 'system')

        volumes = pytsk3.Volume_Info(self.img_info)
        self.block_size = volumes.info.block_size

        result: List[NtfsVolume] = []
        for volume in volumes:
            description = volume.desc.decode('utf-8')
            if not is_ntfs_volume_description(description):
                continue
            try:
                fs_info = pytsk3.FS_Info(
                    self.img_info,
                    self.block_size * volume.start,
                    pytsk3.TSK_FS_TYPE_NTFS,
                )
            except Exception:
                # The description marked this as an NTFS candidate (e.g. a GPT
                # "Basic data partition"), but the volume is not NTFS formatted.
                continue
            result.append(
                NtfsVolume(
                    path=self.resolved.path,
                    addr=volume.addr,
                    description=description,
                    start_byte=volume.start,
                    end_byte=volume.start + volume.len - 1,
                    fs_info=fs_info,
                )
            )

        if not result:
            raise NtfsDumpError("No NTFS volume was found.")

        return result

    def __auto_detect_main_partition(self, volume_num: Optional[int]) -> NtfsVolume:
        if volume_num is not None:
            for item in self.volumes:
                if item.addr == volume_num:
                    return item
            raise NtfsDumpError(f"NTFS volume {volume_num} was not found.")
        elif len(self.volumes) == 1:
            # windows xp ~ vista
            return self.volumes[0]
        else:
            # windows 7 ~ or generalized: because first ntfs partition is usually recovery
            return self.volumes[-1]
