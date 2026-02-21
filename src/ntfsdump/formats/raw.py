# coding: utf-8
import pytsk3
from ntfsdump.formats.base import FormatHandler

class RawHandler(FormatHandler):
    def get_img_info(self, path: str) -> pytsk3.Img_Info:
        return pytsk3.Img_Info(path)
