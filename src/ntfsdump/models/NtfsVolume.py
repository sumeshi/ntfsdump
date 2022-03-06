# coding: utf-8
from pathlib import Path
from typing import List, Optional

import pytsk3


class NtfsVolume(object):

    def __init__(self, path: Path, addr: int, description: str, start_byte: int, end_byte: int, fs_info: pytsk3.FS_Info):
        self.path = path
        self.addr = addr
        self.description = description
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.fs_info = fs_info
    
    def __is_dir(self, query: str) -> bool:
        f = self.fs_info.open(query)
        return True if f.info.name.type == pytsk3.TSK_FS_NAME_TYPE_DIR else False

    def __is_file(self, query: str) -> bool:
        f = self.fs_info.open(query)
        return True if f.info.name.type == pytsk3.TSK_FS_NAME_TYPE_REG else False
    
    def __list_artifacts(self, query: str) -> List[str]:
        # return artifacts without current and parent dir
        return [
            a.info.name.name.decode('utf-8') for a in self.fs_info.open_dir(query) 
            if not a.info.name.name.decode('utf-8') in ['.', '..']
        ]
    
    def __read_file(self, query: str) -> bytes:

        f = self.fs_info.open(query)

        offset = 0
        size = f.info.meta.size
        BUFF_SIZE = 1024 * 1024

        result = bytes()

        while offset < size:
            available_to_read = min(BUFF_SIZE, size - offset)
            data = f.read_random(offset, available_to_read)
            if not data: break

            offset += len(data)
            result += data
        
        return result
    
    def __read_alternate_data_stream(self, query: str, ads: str) -> Optional[bytes]:
        query = query.replace('\\', '/')
        f = self.fs_info.open(query)

        OFFSET = 0
        BUFF_SIZE = 1024 * 1024

        ads_attribute = None
        for attribute in f:
            if attribute.info.name == ads.encode('utf-8'):
                ads_attribute = attribute
                break
        
        if ads_attribute:
            result = bytes()
            ADS_SIZE = ads_attribute.info.size

            while OFFSET < ADS_SIZE:
                available_to_read = min(BUFF_SIZE, ADS_SIZE - OFFSET)
                data = f.read_random(OFFSET, available_to_read, ads_attribute.info.type, ads_attribute.info.id)
                if not data: break
                OFFSET += len(data)
                result += data
            return result
        
        return None
    
    def __write_file(self, destination_path: Path, content: Optional[bytes], filename: str) -> None:
        # destination path is a file
        try:
            destination_path.write_bytes(content)
            print(f"dumped: {destination_path}")

        # destination path is a directory
        except IsADirectoryError:
            Path(destination_path / filename).write_bytes(content)
            print(f"dumped: {Path(destination_path / filename)}")

    def dump_files(self, query: str, destination_path: Path) -> None:
        query = query.replace('\\', '/')

        if self.__is_dir(query):
            for artifact in self.__list_artifacts(query):
                newquery = str(Path(query) / Path(artifact))
                newdestination_path = destination_path / Path(query).name

                # create directory
                newdestination_path.mkdir(parents=True, exist_ok=True)

                # recursive dump
                self.dump_files(query=newquery, destination_path=newdestination_path)

        elif self.__is_file(query):
            filename = Path(query).name
            content = None

            # Alternate Data Stream
            if ':' in filename:
                filepath = query.split(':')[0]
                ads = query.split(':')[1]
                content = self.__read_alternate_data_stream(filepath, ads)
            else:
                content = self.__read_file(query)
            
            if destination_path.name == filename:
                self.__write_file(destination_path, content, filename)
            else:
                destination_path = destination_path / filename
                self.__write_file(destination_path, content, filename)
        
        elif query.endswith('.*'):
            parent_dir = str(Path(query.replace('.*', '')).parent).replace('\\', '/')
            file_prefix = Path(query.replace('.*', '')).name

            files = [artifact for artifact in self.__list_artifacts(parent_dir) if artifact.startswith(file_prefix)]
            for file in files:
                newquery = str(Path(parent_dir) / Path(file))
                self.dump_files(query=newquery, destination_path=destination_path.parent)

        else:
            try:
                filename = Path(query).name
                content = self.__read_file(query)
                self.__write_file(destination_path, content, filename)
            except Exception as e:
                print(e)
                print(f"dump error: {query}")