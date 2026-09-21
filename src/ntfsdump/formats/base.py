# coding: utf-8
from abc import ABC, abstractmethod
from typing import Any, Optional

import pytsk3


class BaseImgInfo(pytsk3.Img_Info):
    def __init__(self, handle, keepalive: Optional[Any] = None):
        self.handle = handle
        # Keep references to any handles (e.g. a VMDK parent chain) alive for
        # as long as this image info object is used.
        self._keepalive = keepalive
        super().__init__(url="", type=pytsk3.TSK_IMG_TYPE_EXTERNAL)

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
