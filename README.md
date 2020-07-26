# ntfsdump

[![MIT License](http://img.shields.io/badge/license-MIT-blue.svg?style=flat)](LICENSE)
[![PyPI version](https://badge.fury.io/py/ntfsdump.svg)](https://badge.fury.io/py/ntfsdump)
[![Python Versions](https://img.shields.io/pypi/pyversions/ntfsdump.svg)](https://pypi.org/project/ntfsdump/)

A tool for exporting any files from an NTFS volume on a Raw Image file.


## Usage

```bash
$ ntfsdump <dump_target_winpath> --output-path <ouput_path> ./path/to/your/imagefile.raw
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
    NTFS volume number(default 2, because volume1 is recovery partition).

--output-path, -o:
    Output directory or file path.

    If the target Path is a directory, the directory specified by --output-path is created and the target files is dump under it.

    Otherwise, the file is dumped with the file name specified in the --output-path.)
```

### Required Software
This software requires `The Sleuth Kit`.

https://www.sleuthkit.org/sleuthkit/

```bash
$ brew install sleuthkit
```

## Installation

### via pip

```
$ pip install ntfsdump
```

The source code for ntfsdump is hosted at GitHub, and you may download, fork, and review it from this repository(https://github.com/sumeshi/ntfsdump).

Please report issues and feature requests. :sushi: :sushi: :sushi:

## License

ntfsdump is released under the [MIT](https://github.com/sumeshi/ntfsdump/blob/master/LICENSE) License.

Powered by [The Sleuth Kit](https://www.sleuthkit.org/sleuthkit/).  