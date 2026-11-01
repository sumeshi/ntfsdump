# coding: utf-8
from pathlib import Path
from typing import List, Optional, Union

import pytsk3

from ntfsdump.errors import NtfsDumpError
from ntfsdump.volume import NtfsVolume
from ntfsdump.logger import get_logger, protect_source_paths
from ntfsdump.sources import SourceResolver, VmwareSource

logger = get_logger()


NTFS_VOLUME_DESCRIPTIONS = (
    # Familiar descriptions retained for callers that want to inspect labels.
    # Partition discovery probes allocated partitions by filesystem instead.
    # MBR: TSK reports NTFS partitions as "NTFS / exFAT (0x07)".
    "NTFS",
    # GPT: TSK labels partitions from their type GUID, not the filesystem.
    # "Basic data partition" (Microsoft basic data) is the usual Windows/NTFS
    # entry; "Windows Recovery Environment" is NTFS as well.
    "Basic data partition",
    "Windows Recovery Environment",
)

# Directory structure that distinguishes a Windows OS volume from recovery,
# data and EFI volumes. The first entry is the primary indicator; a volume is
# considered an OS volume only when it is present together with another one,
# so that a bare data volume carrying a stray "/Windows" folder is not enough.
_OS_INDICATOR_PATHS = (
    "/Windows",
    "/Program Files",
    "/Program Files (x86)",
    "/ProgramData",
    "/Users",
)


def is_ntfs_volume_description(description: str) -> bool:
    """Whether a description resembles a common NTFS partition label.

    This is only a label check: GPT user labels are arbitrary, and the
    partition scanner determines NTFS volumes by opening allocated partitions
    with FS_Info.
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
        self.source_paths = [
            path for path in (Path(source), self.resolved.path) if path.is_file()
        ]
        self.source_paths.extend(getattr(self.img_info, "source_paths", ()))
        if isinstance(self.resolved, VmwareSource):
            self.source_paths.extend(
                path
                for path in (self.resolved.vm.vmx_path, self.resolved.vm.vmsd_path)
                if path is not None
            )
        protect_source_paths(self.source_paths)
        self.volumes = self.__analyze_partitions()
        self.main_volume = self.__auto_detect_main_partition(volume)

        logger.log(
            f"[analyze] {len(self.volumes)} volumes were detected as NTFS volumes.",
            "system",
        )
        for item in self.volumes:
            logger.log(
                f"[analyze] NTFS Volume {item.addr}: {item.description}", "system"
            )
        logger.log(
            f"[analyze] Volume {self.main_volume.addr} "
            "was selected as the main partition.",
            "system",
        )

    def __analyze_partitions(self) -> List[NtfsVolume]:
        logger.log(f"[analyze] {self.resolved.format.upper()} Format Image", "system")

        try:
            volumes = pytsk3.Volume_Info(self.img_info)
        except OSError as exc:
            standalone = self.__standalone_ntfs_volume()
            if standalone is not None:
                return [standalone]
            raise NtfsDumpError("No NTFS volume was found.") from exc
        # Volume_Info's block size defaults to 512 for external images, even
        # when a VHDX backend identifies a 4096 byte logical sector.
        self.block_size = (
            getattr(self.img_info, "logical_sector_size", None)
            or volumes.info.block_size
        )

        result: List[NtfsVolume] = []
        for volume in volumes:
            flags = getattr(volume, "flags", pytsk3.TSK_VS_PART_FLAG_ALLOC)
            if not flags & pytsk3.TSK_VS_PART_FLAG_ALLOC:
                continue
            description = volume.desc.decode("utf-8", errors="replace")
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
            standalone = self.__standalone_ntfs_volume()
            if standalone is None:
                raise NtfsDumpError("No NTFS volume was found.")
            result.append(standalone)

        return result

    def __standalone_ntfs_volume(self) -> Optional[NtfsVolume]:
        """Verify a partition-only image at offset zero without guessing offsets."""
        try:
            fs_info = pytsk3.FS_Info(self.img_info, 0, pytsk3.TSK_FS_TYPE_NTFS)
        except OSError:
            return None
        return NtfsVolume(
            path=self.resolved.path,
            addr=0,
            description="NTFS (partition image)",
            start_byte=0,
            end_byte=max(0, self.img_info.get_size() // self.block_size - 1),
            fs_info=fs_info,
        )

    def __os_volume_markers(self, volume: NtfsVolume) -> bool:
        """Whether an NTFS volume looks like a Windows OS volume.

        Checking the actual directory tree keeps the decision independent of
        GPT/MBR partition labels (e.g. a WinRE partition is also labeled
        "Basic data partition" on some layouts).
        """
        has_windows_dir = False
        markers = 0
        for path in _OS_INDICATOR_PATHS:
            try:
                f = volume.fs_info.open(path)
            except Exception:
                continue
            if f.info.name.type == pytsk3.TSK_FS_NAME_TYPE_DIR:
                markers += 1
                if path == "/Windows":
                    has_windows_dir = True
        return has_windows_dir and markers >= 2

    def __os_volume_candidates(self) -> List[NtfsVolume]:
        return [item for item in self.volumes if self.__os_volume_markers(item)]

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
            # Identify the OS volume from the NTFS directory structure;
            # Windows 10/11 layouts (EFI, MSR, OS, WinRE, data...) must not
            # fall back to a guess such as "the last volume".
            candidates = self.__os_volume_candidates()
            if len(candidates) == 1:
                return candidates[0]

            listing = ", ".join(
                f"{item.addr}: {item.description}" for item in self.volumes
            )
            if not candidates:
                raise NtfsDumpError(
                    f"Multiple NTFS volumes were found, but none of them looks "
                    f"like a Windows OS volume: {listing}. "
                    f"Use --volume to select the main volume explicitly."
                )
            listing = ", ".join(
                f"{item.addr}: {item.description}" for item in candidates
            )
            raise NtfsDumpError(
                f"Multiple NTFS volumes look like Windows OS volumes: "
                f"{listing}. Use --volume to select the main volume explicitly."
            )
