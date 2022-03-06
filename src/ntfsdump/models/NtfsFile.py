# coding: utf-8

class NtfsFile(object):
    def __init__(self, filetype: str, address: str, filename: str):
        self.is_file = self.__is_file(filetype)
        self.address = address.split(":")[0]
        self.filename = filename

    def __is_file(self, filetype: str) -> bool:
        return filetype.startswith("r")