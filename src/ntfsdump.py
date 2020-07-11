import re
import shutil
import argparse
import subprocess
from pathlib import Path
from typing import List, Generator


class NtfsFile(object):
    def __init__(self, filetype: str, address: str, filename: str):
        self.is_file = self.__is_file(filetype)
        self.address = address.split(":")[0]
        self.filename = filename

    def __is_file(self, filetype: str) -> bool:
        return filetype.startswith("r")


class NtfsVolume(object):
    def __init__(self, path: Path, description: str, start_byte: int, end_byte: int):
        self.path = path
        self.description = description
        self.start_byte = start_byte
        self.end_byte = end_byte

    def __ls(self, option: str = "", address: str = "") -> List[NtfsFile]:
        ls = subprocess.check_output(
            f"fls -i raw -f ntfs -o {self.start_byte} {option} {self.path} {address}",
            shell=True,
        )
        data_list = [line.split() for line in grepline(ls, "")]
        return [
            NtfsFile(filetype=data[0], address=data[1], filename=data[2],)
            for data in data_list
        ]

    def __write_file(self, file_path: Path, address: str):
        print(f"write: {file_path}")
        file_content = subprocess.check_output(
            f"icat -i raw -f ntfs -o {self.start_byte} {self.path} {address}",
            shell=True,
        )
        file_path.write_bytes(file_content)

    def __recursive_dump(self, destination_path: Path, address: str):
        for directory in self.__ls(option="-D", address=address):
            Path(destination_path, directory.filename).mkdir(
                parents=True, exist_ok=True
            )
            self.__recursive_dump(
                Path(destination_path, directory.filename), directory.address
            )

        for file in self.__ls(option="-F", address=address):
            try:
                self.__write_file(Path(destination_path, file.filename), file.address)
            except FileNotFoundError:
                Path(destination_path).mkdir(parents=True, exist_ok=True)
                self.__write_file(Path(destination_path, file.filename), file.address)

    def find_baseaddress(self, path_list: List[str], address: str = "") -> str:
        if not path_list:
            return address

        found_contents = [
            content
            for content in self.__ls(address=address)
            if content.filename == path_list[0]
        ]

        if found_contents:
            return self.find_baseaddress(path_list[1:], found_contents[0].address)
        else:
            raise Exception("File or Directory not Found")

    def dump_files(self, query: str, destination_path: Path, address: str = "") -> None:
        queries = [q for q in query.split("/") if q]
        base_address = self.find_baseaddress(queries)

        try:
            # is_dir
            self.__ls(address=base_address)
            self.__recursive_dump(destination_path, base_address)
        except Exception:
            # is_file
            self.__write_file(destination_path, base_address)


class ImageFile(object):
    def __init__(self, path: Path):
        self.path = path
        self.volumes = self.__analyze_partitions()

    def __analyze_partitions(self) -> List[NtfsVolume]:
        volumes = subprocess.check_output(f"mmls {self.path}", shell=True)
        pattern = re.compile(r"^\d\d\d:.*")
        data_list = [line.split() for line in grepline(volumes, "NTFS", pattern)]
        return [
            NtfsVolume(
                path=self.path,
                description=" ".join(data[5:]),
                start_byte=int(data[2]),
                end_byte=int(data[3]),
            )
            for data in data_list
        ]


def grepline(
    msg: bytes, key: str, validate_pattern: re.Pattern = re.compile(r".*")
) -> List[str]:
    return [
        line
        for line in msg.decode("utf8").splitlines()
        if key in line and re.match(validate_pattern, line)
    ]


def ntfsdump():

    if not shutil.which("mmls"):
        print(
            "The Sleuth Kit is not installed. Please execute the command `brew install sleuthkit`"
        )
        exit()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "target_query",
        type=str,
        help="Target File Windows Path (ex. /Users/user/Desktop/target.txt).",
    )
    parser.add_argument("imagefile_path", type=Path, help="raw image file")
    parser.add_argument(
        "--volume-num",
        "-n",
        type=int,
        default=2,
        help="NTFS volume number(default: 2, because volume1 is recovery partition).",
    )
    parser.add_argument(
        "--output-path",
        "-o",
        type=Path,
        default=Path(".").resolve(),
        help="Output directory or file path.",
    )
    args = parser.parse_args()

    i = ImageFile(args.imagefile_path)
    i.volumes[args.volume_num - 1].dump_files(
        args.target_query, args.output_path.resolve()
    )


if __name__ == "__main__":
    ntfsdump()
