# coding: utf-8
from typing import Dict, Type

from ntfsdump.formats.base import FormatHandler
from ntfsdump.formats.raw import RawHandler
from ntfsdump.formats.e01 import E01Handler
from ntfsdump.formats.vhd import VHDHandler
from ntfsdump.formats.vmdk import VMDKHandler


def get_format_handler(file_type: str) -> FormatHandler:
    """Instantiate and return the appropriate image format handler."""
    handlers: Dict[str, Type[FormatHandler]] = {
        'raw': RawHandler,
        'e01': E01Handler,
        'vhd': VHDHandler,
        'vhdx': VHDHandler,
        'vmdk': VMDKHandler,
    }
    
    handler_cls = handlers.get(file_type.lower(), RawHandler)
    return handler_cls()

__all__ = ["get_format_handler", "FormatHandler"]
