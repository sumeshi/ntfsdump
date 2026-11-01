# coding: utf-8
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

import pytsk3


class BaseImgInfo(pytsk3.Img_Info):
    def __init__(self, handle, keepalive: Optional[Any] = None, source_paths=()):
        self.handle = handle
        self.source_paths = tuple(Path(path) for path in source_paths)
        # Keep references to any handles (e.g. a VMDK parent chain) alive for
        # as long as this image info object is used.
        self._keepalive = keepalive
        # libtsk's external image wrapper reports a default 512 byte sector
        # size. Preserve the backend's geometry when it knows the disk is 4Kn.
        self.logical_sector_size = None
        try:
            sector_size = int(handle.get_bytes_per_sector())
            if sector_size > 0:
                self.logical_sector_size = sector_size
        except (AttributeError, OSError, TypeError, ValueError):
            pass
        img_options = {"url": "", "type": pytsk3.TSK_IMG_TYPE_EXTERNAL}
        if self.logical_sector_size is not None:
            img_options["sector_size"] = self.logical_sector_size
        super().__init__(**img_options)

    def close(self):
        handles = self._keepalive if self._keepalive else [self.handle]
        for handle in handles:
            try:
                handle.close()
            except Exception:
                pass

    def read(self, offset, size):
        self.handle.seek(offset)
        return self.handle.read(size)

    def get_size(self):
        return self.handle.get_media_size()


class FormatHandler(ABC):
    @abstractmethod
    def get_img_info(self, path: str) -> pytsk3.Img_Info:
        """Parse image file and return pytsk3.Img_Info"""
        pass
