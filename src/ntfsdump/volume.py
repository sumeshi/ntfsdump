# coding: utf-8
import pytsk3
from pathlib import Path
from typing import List, Optional

from ntfsdump.logger import get_logger


logger = get_logger()


class NtfsVolume:
    def __init__(
        self,
        path: Path,
        addr: int,
        description: str,
        start_byte: int,
        end_byte: int,
        fs_info: pytsk3.FS_Info
    ):
        self.path = path
        self.addr = addr
        self.description = description
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.fs_info = fs_info
    
    def __clean_query(self, query: str) -> str:
        cleaned = query.replace('\\', '/')
        if not cleaned.startswith('/'):
            cleaned = '/' + cleaned
        return cleaned
    
    def __is_dir(self, query: str) -> bool:
        f = self.fs_info.open(query)
        return f.info.name.type == pytsk3.TSK_FS_NAME_TYPE_DIR

    def __is_file(self, query: str) -> bool:
        f = self.fs_info.open(query)
        return f.info.name.type == pytsk3.TSK_FS_NAME_TYPE_REG
    
    def __list_artifacts(self, query: str) -> List[str]:
        # return artifacts without current and parent dir
        return [
            a.info.name.name.decode('utf-8') for a in self.fs_info.open_dir(query) 
            if a.info.name.name.decode('utf-8') not in ['.', '..']
        ]
    
    def __read_file(self, query: str) -> bytes:
        f = self.fs_info.open(query)

        offset = 0
        size = f.info.meta.size
        BUFF_SIZE = 1024 * 1024

        result = bytearray()

        while offset < size:
            available_to_read = min(BUFF_SIZE, size - offset)
            data = f.read_random(offset, available_to_read)
            if not data:
                break

            offset += len(data)
            result.extend(data)
        
        return bytes(result)
    
    def __read_alternate_data_stream(self, query: str, ads: str) -> Optional[bytes]:
        f = self.fs_info.open(query)

        offset = 0
        BUFF_SIZE = 1024 * 1024

        ads_attribute = None
        for attribute in f:
            if attribute.info.name == ads.encode('utf-8'):
                ads_attribute = attribute
                break
        
        if ads_attribute:
            result = bytearray()
            ADS_SIZE = ads_attribute.info.size

            while offset < ADS_SIZE:
                available_to_read = min(BUFF_SIZE, ADS_SIZE - offset)
                data = f.read_random(offset, available_to_read, ads_attribute.info.type, ads_attribute.info.id)
                if not data:
                    break
                offset += len(data)
                result.extend(data)
            return bytes(result)
        
        return None
    
    def __write_file(self, destination_path: Path, content: Optional[bytes], filename: str) -> None:
        if content is None:
            content = b""

        # destination path is a file
        try:
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            destination_path.write_bytes(content)
            logger.log(f"[dumped] {destination_path}", 'info')

        # destination path is a directory
        except IsADirectoryError:
            target = destination_path / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            logger.log(f"[dumped] {target}", 'info')

    def dump_files(self, query: str, destination_path: Path, flat: bool = False) -> None:
        query = self.__clean_query(query)
        logger.log(f"[query] {query}", 'system')

        if self.__is_dir(query):
            for artifact in self.__list_artifacts(query):
                newquery = str(Path(query) / artifact)
                # recursive dump
                self.dump_files(query=newquery, destination_path=destination_path, flat=flat)

        elif self.__is_file(query):
            filename = Path(query).name
            content = None

            # Alternate Data Stream
            if ':' in filename:
                filepath, ads = query.split(':', 1)
                content = self.__read_alternate_data_stream(filepath, ads)
            else:
                content = self.__read_file(query)
            
            if destination_path.name == filename:
                self.__write_file(destination_path, content, filename)
            else:
                if flat:
                    self.__write_file(destination_path / filename, content, filename)
                else:
                    # Always recreate the directory tree using relative path
                    q_path = Path(query.lstrip('/'))
                    self.__write_file(destination_path / q_path, content, filename)
        
        elif query.endswith('.*'):
            base_query = query.replace('.*', '')
            parent_dir = str(Path(base_query).parent).replace('\\', '/')
            file_prefix = Path(base_query).name

            files = [
                artifact for artifact in self.__list_artifacts(parent_dir) 
                if artifact.startswith(file_prefix)
            ]
            for file in files:
                newquery = str(Path(parent_dir) / file)
                self.dump_files(query=newquery, destination_path=destination_path, flat=flat)

        else:
            try:
                filename = Path(query).name
                content = self.__read_file(query)
                if destination_path.name == filename:
                    self.__write_file(destination_path, content, filename)
                else:
                    if flat:
                        self.__write_file(destination_path / filename, content, filename)
                    else:
                        q_path = Path(query.lstrip('/'))
                        self.__write_file(destination_path / q_path, content, filename)
            except Exception as e:
                logger.log(f"[error] {query}", 'danger')
                logger.log(str(e), 'danger')
