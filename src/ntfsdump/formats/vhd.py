# coding: utf-8
import pyvhdi
import pytsk3
from ntfsdump.formats.base import FormatHandler, BaseImgInfo

class VHDHandler(FormatHandler):
    def get_img_info(self, path: str) -> pytsk3.Img_Info:
        vhdi_file = pyvhdi.file()
        vhdi_file.open(path)
        return BaseImgInfo(vhdi_file)
