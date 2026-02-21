# coding: utf-8
import pyewf
import pytsk3
from ntfsdump.formats.base import FormatHandler, BaseImgInfo

class E01Handler(FormatHandler):
    def get_img_info(self, path: str) -> pytsk3.Img_Info:
        filenames = pyewf.glob(path)
        ewf_handle = pyewf.handle()
        ewf_handle.open(filenames)
        return BaseImgInfo(ewf_handle)
