# coding: utf-8
import pyvmdk
import pytsk3
from ntfsdump.formats.base import FormatHandler, BaseImgInfo


class VMDKHandler(FormatHandler):
    def get_img_info(self, path: str) -> pytsk3.Img_Info:
        # Currently supports only a single vmdk base or main snapshot opening.
        # Can be expanded to traverse trees and snapshots in the future.
        vmdk_handle = pyvmdk.handle()
        vmdk_handle.open(path)
        vmdk_handle.open_extent_data_files()
        return BaseImgInfo(vmdk_handle)
