# coding: utf-8
from typing import Dict, Type

from ntfsdump.errors import NtfsDumpError
from ntfsdump.formats.base import FormatHandler
from ntfsdump.formats.raw import RawHandler
from ntfsdump.formats.e01 import E01Handler
from ntfsdump.formats.vhd import VHDHandler
from ntfsdump.formats.vmdk import VMDKHandler


VALID_IMAGE_FORMATS = ('raw', 'e01', 'vhd', 'vhdx', 'vmdk')


def get_format_handler(file_type: str) -> FormatHandler:
    """Instantiate and return the appropriate image format handler.

    Unknown formats raise instead of silently falling back to RawHandler.
    """
    handlers: Dict[str, Type[FormatHandler]] = {
        'raw': RawHandler,
        'e01': E01Handler,
        'vhd': VHDHandler,
        'vhdx': VHDHandler,
        'vmdk': VMDKHandler,
    }

    handler_cls = handlers.get((file_type or '').lower())
    if handler_cls is None:
        raise NtfsDumpError(f"Unknown image format: {file_type}")
    return handler_cls()


__all__ = ["get_format_handler", "FormatHandler", "VALID_IMAGE_FORMATS"]
