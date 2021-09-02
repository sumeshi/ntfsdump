import re
import sys
import shutil
import argparse
import subprocess
from pathlib import Path
from typing import List, Generator, Optional

import pytsk3

class NtfsFile(object):
    def __init__(self, filetype: str, address: str, filename: str):
        self.is_file = self.__is_file(filetype)
        self.address = address.split(":")[0]
        self.filename = filename

    def __is_file(self, filetype: str) -> bool:
        return filetype.startswith("r")


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
    
    def __write_file(self, destination_path: Path, content: bytes, filename: str) -> None:
        # destination path is a file
        try:
            destination_path.write_bytes(content)
            print(f"dumped: {destination_path}")

        # destination path is a directory
        except IsADirectoryError:
            Path(destination_path / filename).write_bytes(content)
            print(f"dumped: {Path(destination_path / filename)}")

    def dump_files(self, query: str, destination_path: Path) -> None:

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
            content = self.__read_file(query)
            self.__write_file(destination_path, content, filename)
        else:
            try:
                filename = Path(query).name
                content = self.__read_file(query)
                self.__write_file(destination_path, content, filename)
            except:
                print(f"dump error: {query}")


class ImageFile(object):
    def __init__(self, path: Path, volume_num: Optional[int]):
        self.path: Path = path
        self.block_size: int = 512
        self.volumes: List[NtfsVolume] = self.__analyze_partitions()
        self.main_volume: NtfsVolume = self.__auto_detect_main_partition(volume_num)

    def __analyze_partitions(self) -> List[NtfsVolume]:
        img_info = pytsk3.Img_Info(str(self.path))
        volumes = pytsk3.Volume_Info(img_info)

        self.block_size = volumes.info.block_size

        return [
            NtfsVolume(
                path=self.path,
                addr=volume.addr,
                description=volume.desc.decode('utf-8'),
                start_byte=volume.start,
                end_byte=volume.start+volume.len-1,
                fs_info=pytsk3.FS_Info(img_info, self.block_size * volume.start, pytsk3.TSK_FS_TYPE_NTFS)
            ) for volume in volumes if volume.desc.decode('utf-8').startswith('NTFS')
        ]
    
    def __auto_detect_main_partition(self, volume_num: Optional[int]) -> NtfsVolume:
        if volume_num:
            # user specify addr
            return [v for v in self.volumes if v.addr == volume_num][0]

        elif len(self.volumes) == 1:
            # windows xp ~ vista
            return self.volumes[0]

        elif len(self.volumes) == 2:
            # windows 7 ~
            # bacause first ntfs partition is recovery partition.
            return self.volumes[-1]

        else:
            return self.volumes[-1]


def ntfsdump(imagefile_path: str, output_path: str, target_queries: List[str], volume_num: Optional[int] = None):
    # dump files
    image = ImageFile(Path(imagefile_path), volume_num)
    for target_query in target_queries:
        image.main_volume.dump_files(
            target_query, Path(output_path).resolve()
        )
    
def entry_point():
    parser = argparse.ArgumentParser()

    # If no queries have been received from the pipeline.
    if sys.stdin.isatty():
        parser.add_argument(
            "target_queries",
            nargs="+",
            type=str,
            help="Target File Windows Path (ex. /Users/user/Desktop/target.txt).",
        )

    parser.add_argument("imagefile_path", type=str, help="raw image file")
    parser.add_argument(
        "--volume-num",
        "-n",
        type=int,
        default=None,
        help="NTFS volume number(default: autodetect).",
    )
    parser.add_argument(
        "--output-path",
        "-o",
        type=str,
        default=".",
        help="Output directory or file path(default: current directory \'.\' ).",
    )
    args = parser.parse_args()

    # pipeline stdin or args
    target_queries = [i.strip() for i in sys.stdin] if not sys.stdin.isatty() else args.target_queries

    ntfsdump(
        imagefile_path=args.imagefile_path,
        output_path=args.output_path,
        target_queries=target_queries,
        volume_num=args.volume_num
    )


if __name__ == "__main__":
    entry_point()
