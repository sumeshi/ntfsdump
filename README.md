# ntfsdump

[![MIT License](http://img.shields.io/badge/license-MIT-blue.svg?style=flat)](LICENSE)
[![PyPI version](https://badge.fury.io/py/ntfsdump.svg)](https://badge.fury.io/py/ntfsdump)
[![Python Versions](https://img.shields.io/pypi/pyversions/ntfsdump.svg)](https://pypi.org/project/ntfsdump/)
[![pytest](https://github.com/sumeshi/ntfsdump/actions/workflows/test.yaml/badge.svg)](https://github.com/sumeshi/ntfsdump/actions/workflows/test.yaml)

![ntfsdump logo](https://gist.githubusercontent.com/sumeshi/c2f430d352ae763273faadf9616a29e5/raw/baa85b045e0043914218cf9c0e1d1722e1e7524b/ntfsdump.svg)

An efficient tool for extracting files, directories, and alternate data streams directly from NTFS image files.


## Usage

**ntfsdump** can be executed from the command line or incorporated into a Python script.

```bash
$ ntfsdump {{query}} --output-path {{output_dir}} /path/to/imagefile.raw
```

```python
from ntfsdump import ntfsdump

# imagefile_path: str
# output_path: str
# target_queries: List[str]
# volume_num: Optional[int] = None
# file_type: Literal['raw', 'e01', 'vhd', 'vhdx', 'vmdk'] = 'raw'

ntfsdump(
    imagefile_path='./path/to/your/imagefile.raw',
    output_path='./path/to/output/directory',
    target_queries=['/Windows/System32/winevt/Logs'],
    volume_num=2,
    file_type='raw'
)
```

### Query

This tool allows you to search for and extract file, directory, and ADS paths using regular expression queries.  
Paths are separated by forward slashes (Unix/Linux-style) rather than backslashes (Windows-style).

e.g.
```
Original Path: C:\$MFT
Query: /$MFT

Original Path: C:\$Extend\$UsnJrnl\$J
Query: /$Extend/$UsnJrnl/$J

Original Path: C:\Windows\System32\winevt\Logs
Query: /Windows/System32/winevt/Logs
```

Queries will be expanded in the future.  
If you have any questions, please feel free to submit an issue.

### Example
The target path can either be standalone or within a directory.  
In the case of a directory, it recursively dumps the files within it.

```.bash
$ ntfsdump /Windows/System32/winevt/Logs -o ./dump ./path/to/your/imagefile.raw
```

extracting from E01 image (included splited-E01).

```.bash
$ ls
imagefile.E01
imagefile.E02
imagefile.E03
imagefile.E04
imagefile.E05

$ ntfsdump /Windows/System32/winevt/Logs --type=e01 -o ./dump ./path/to/your/imagefile.E01
```

#### When use with [ntfsfind](https://github.com/sumeshi/ntfsfind)

https://github.com/sumeshi/ntfsfind

```.bash
$ ntfsfind '.*\.evtx' ./path/to/your/imagefile.raw | ntfsdump ./path/to/your/imagefile.raw
```

### Options
```
--help, -h:
    Display the help message and exit.

--version, -v:
    Display the program's version number and exit.

--quiet, -q:
    Flag to suppress standard output.

--nolog:
    Flag to prevent any logs from being output.

--volume-num, -n:
    NTFS volume number (default: autodetect).

--type, -t:
    Image file format (default: raw(dd-format)).
    Supported formats are (raw|e01|vhd|vhdx|vmdk).

--output-path, -o:
    Output directory or file path.

    If the target path is a directory, the directory specified by --output-path is created, and the target files are dumped under it.

    Otherwise, the file is dumped with the filename specified in --output-path.
```

## Prerequisites
The image file to be processed must meet the following conditions:

- The file format must be raw, e01, vhd, vhdx, or vmdk.
- It must use the NTFS (NT File System).
- It must have a GUID Partition Table (GPT).

Additional file formats will be added in the future.  
If you have any questions, please feel free to submit an issue.


## LogFormat
**ntfsdump** outputs logs in the following format.  
By default, it outputs the files to the current directory, but if you do not need them, please use the `--nolog` option.

```
- ntfsdump v{{version}} - 
2022-01-01T00:00:00.000000: [{{EventName}}] {{Description}}
2022-01-01T00:00:00.000000: [{{EventName}}] {{Description}}
2022-01-01T00:00:00.000000: [{{EventName}}] {{Description}}
...
```

## Installation

### from PyPI

```bash
$ pip install ntfsdump
```

### from GitHub Releases
The version compiled into a binary using Nuitka is also available for use.

```bash
$ chmod +x ./ntfsdump
$ ./ntfsdump {{options...}}
```

```bat
> ntfsdump.exe {{options...}}
```

## Contributing

The source code for ntfsdump is hosted at GitHub, and you may download, fork, and review it from this repository(https://github.com/sumeshi/ntfsdump).

Please report issues and feature requests. :sushi: :sushi: :sushi:

## License

ntfsdump is released under the [LGPLv3+](https://github.com/sumeshi/ntfsdump/blob/master/LICENSE) License.

Powered by following libraries.
- [pytsk3](https://github.com/py4n6/pytsk)
- [libewf](https://github.com/libyal/libewf)
- [libvhdi](https://github.com/libyal/libvhdi)
- [libvmdk](https://github.com/libyal/libvmdk)
- [ntfs-samples](https://github.com/msuhanov/ntfs-samples)
- [Nuitka](https://github.com/Nuitka/Nuitka)
