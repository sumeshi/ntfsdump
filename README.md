# ntfsdump

[![MIT License](http://img.shields.io/badge/license-MIT-blue.svg?style=flat)](LICENSE)
[![PyPI version](https://badge.fury.io/py/ntfsdump.svg)](https://badge.fury.io/py/ntfsdump)
[![Python Versions](https://img.shields.io/pypi/pyversions/ntfsdump.svg)](https://pypi.org/project/ntfsdump/)
[![DockerHub Status](https://shields.io/docker/cloud/build/sumeshi/ntfsdump)](https://hub.docker.com/r/sumeshi/ntfsdump)

![ntfsdump logo](https://gist.githubusercontent.com/sumeshi/c2f430d352ae763273faadf9616a29e5/raw/baa85b045e0043914218cf9c0e1d1722e1e7524b/ntfsdump.svg)

A tool for exporting any files from an NTFS volume on a Raw Image file.


## Usage

```bash
$ ntfsdump <dump_target_winpath> --output-path <ouput_path> ./path/to/your/imagefile.raw
```

```python
from ntfsfind import ntfsfind

# imagefile_path: str
# output_path: str
# target_queries: List[str]
# volume_num: Optional[int] = None

ntfsdump(
    imagefile_path='./path/to/your/imagefile.raw',
    output_path='./path/to/output/directory',
    target_queries=['/Windows/System32/winevt/Logs'],
    volume_num=2
)
```

### Example
The target path can be either alone or in a directory.
In the case of a directory, it dumps the lower files recursively.

```.bash
$ ntfsdump /Windows/System32/winevt/Logs -o ./dump ./path/to/your/imagefile.raw
```


#### When use with [ntfsfind](https://github.com/sumeshi/ntfsfind)

https://github.com/sumeshi/ntfsfind

```.bash
$ ntfsfind '.*\.evtx' ./path/to/your/imagefile.raw | ntfsdump ./path/to/your/imagefile.raw
```

### Options
```
--volume-num, -n:
    NTFS volume number(default: autodetect).

--output-path, -o:
    Output directory or file path.

    If the target Path is a directory, the directory specified by --output-path is created and the target files is dump under it.

    Otherwise, the file is dumped with the file name specified in the --output-path.)
```

## Installation

### via PyPI

```
$ pip install ntfsdump
```

## Run with Docker
https://hub.docker.com/r/sumeshi/ntfsdump


```bash
$ docker run -t --rm -v $(pwd):/app/work sumeshi/ntfsdump:latest '/$MFT' /app/work/sample.raw
```

## Contributing

The source code for ntfsdump is hosted at GitHub, and you may download, fork, and review it from this repository(https://github.com/sumeshi/ntfsdump).

Please report issues and feature requests. :sushi: :sushi: :sushi:

## License

ntfsdump is released under the [MIT](https://github.com/sumeshi/ntfsdump/blob/master/LICENSE) License.

Powered by [pytsk3](https://github.com/py4n6/pytsk).  