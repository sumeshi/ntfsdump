# coding: utf-8
from abc import ABC, abstractmethod
import pytsk3


class BaseImgInfo(pytsk3.Img_Info):
    def __init__(self, handle):
        self.handle = handle
        super().__init__(url="", type=pytsk3.TSK_IMG_TYPE_EXTERNAL)

    def close(self):
        self.handle.close()

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
