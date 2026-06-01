# ntfsdump

[![MIT License](http://img.shields.io/badge/license-MIT-blue.svg?style=flat)](LICENSE)
[![PyPI Version](https://img.shields.io/pypi/v/ntfsdump)](https://pypi.org/project/ntfsdump/)
[![pytest](https://img.shields.io/github/actions/workflow/status/sumeshi/ntfsdump/test.yaml)](https://github.com/sumeshi/ntfsdump/blob/master/.github/workflows/test.yaml)

![ntfsdump logo](https://gist.githubusercontent.com/sumeshi/c2f430d352ae763273faadf9616a29e5/raw/baa85b045e0043914218cf9c0e1d1722e1e7524b/ntfsdump.svg)

A command-line tool for efficiently extracting files, directories, and alternate data streams directly from NTFS image files.

## Overview

`ntfsdump` is a command-line tool and Python library for extracting files, directories, and alternate data streams from NTFS volumes in disk images without mounting them.

It supports common forensic image formats such as RAW, E01, VHD/VHDX, and VMDK through `pytsk3` and libraries from the `libyal` project.


## Features

- Extract files directly from NTFS volumes in disk images
- Dump a single file, multiple files, or an entire directory recursively
- Extract alternate data streams (ADS)
- Reconstruct the original directory structure in the output directory
- Supports `RAW`, `E01`, `VHD`, `VHDX`, and `VMDK ` image formats
- Read paths from standard input for integration with tools such as `ntfsfind`
- Use as a command-line tool or Python library


## Installation

```bash
# From PyPI
pip install ntfsdump

# From GitHub Releases (Precompiled Binaries)
chmod +x ./ntfsdump
./ntfsdump --help
```


## Supported Input

- Image formats: `RAW`, `E01`, `VHD`, `VHDX`, `VMDK`
- File system: `NTFS`
- Partition tables: GPT is supported; MBR may be auto-detected depending on the image


## Usage

### Command Line Interface

You can pass arguments directly to the CLI. The output path can be either a file path or a directory path.

```bash
ntfsdump [OPTIONS] <IMAGE> [PATHS...]
```

**Options**:
- `--help`, `-h`: Show help message.
- `--version`, `-V`: Display program version.
- `--quiet`, `-q`: Suppress stdout output.
- `--no-log`: Prevent log file creation.
- `--flat`: Extract all artifacts purely into a single folder without reconstructing directories.
- `--volume`, `-n`: Target specific NTFS volume number (default: auto-detects main OS volume).
- `--format`, `-f`: Image file format (default: `raw`). Options: `raw`, `e01`, `vhd`, `vhdx`, `vmdk`.
- `--output`, `-o`: Directory or file to save exported outputs.


#### Examples

Dump a single file:

```bash
ntfsdump -o ./dump ./path/to/your/image.raw /$MFT
```

Dump an entire directory recursively:

```bash
ntfsdump -o ./dump ./path/to/your/image.raw /Windows/System32/winevt/Logs
```

Extract from split E01 images by providing the starting `.E01` segment:

```bash
ntfsdump --format=e01 -o ./dump ./path/to/your/image.E01 /Windows/System32/winevt/Logs
```

Using with [ntfsfind](https://github.com/sumeshi/ntfsfind) over standard input (pipe):

```bash
ntfsfind '.*\.evtx' ./image.raw | ntfsdump -o ./dump ./image.raw
```

*Note: Any absolute path (starting with `/` or `\`) passed over stdin via tools like `ntfsfind` will automatically be cleaned, and the folder hierarchy will be rebuilt faithfully inside your local output directory (`./dump/Windows/System32/winevt/Logs/System.evtx`).*


### Python Module

You can incorporate `ntfsdump` logic into your own scripts.

```python
from ntfsdump import ntfsdump

ntfsdump(
    image='./path/to/your/image.raw',
    paths=['/Windows/System32/winevt/Logs'],
    output='./dump',
    volume=2,
    format='raw'
)
```


## Query Syntax

`ntfsdump` uses UNIX-like path separators (`/`) for queries. Depending on the image and backend behavior, path matching may be case-sensitive.

- **File**: `/$MFT` -> extracts `$MFT`
- **ADS**: `/$Extend/$UsnJrnl:$J` -> extracts the `$J` ADS file from `$UsnJrnl`.
- **Directory**: `/Windows/System32/winevt/Logs` -> extracts all event logs recursively.
- **Prefix Expansion**: `/Windows/Prefetch/.*` -> extracts all files located in the `Prefetch` directory.


## Logs

By default, an execution log (e.g. `ntfsdump_20240101_153205_1234.log`) is generated in the current directory to safely record which files were successfully dumped or failed.
*To disable logging entirely, append the `--no-log` flag.*


## Contributing

We welcome bug reports, issues, and feature requests. Please submit them on the [GitHub repository](https://github.com/sumeshi/ntfsdump). :sushi: :sushi: :sushi:


## License

ntfsdump is released under the [MIT](LICENSE) License.

Powered by:
- [pytsk](https://github.com/py4n6/pytsk)
- [libewf](https://github.com/libyal/libewf)
- [libvhdi](https://github.com/libyal/libvhdi)
- [libvmdk](https://github.com/libyal/libvmdk)


### Third-party licenses

The standalone binaries distributed via GitHub Releases bundle the following third-party libraries.


#### LGPL-3.0-or-later

The following libyal libraries are licensed under the [GNU Lesser General Public License v3.0 or later (LGPL-3.0-or-later)](https://www.gnu.org/licenses/lgpl-3.0.html).
You may obtain, modify, and rebuild them from their upstream sources in accordance with the LGPL.

- [libewf / libewf-python](https://github.com/libyal/libewf)
  - Bundled version: [`libewf-python==20240506`](https://pypi.org/project/libewf-python/20240506/) (source: https://github.com/libyal/libewf/releases/tag/20240506)
  - License text: https://github.com/libyal/libewf/blob/main/COPYING.LESSER
- [libvhdi / libvhdi-python](https://github.com/libyal/libvhdi)
  - Bundled version: [`libvhdi-python==20251119`](https://pypi.org/project/libvhdi-python/20251119/) (source: https://github.com/libyal/libvhdi/releases/tag/20251119)
  - License text: https://github.com/libyal/libvhdi/blob/main/COPYING.LESSER
- [libvmdk / libvmdk-python](https://github.com/libyal/libvmdk)
  - Bundled version: [`libvmdk-python==20240510`](https://pypi.org/project/libvmdk-python/20240510/) (source: https://github.com/libyal/libvmdk/releases/tag/20240510)
  - License text: https://github.com/libyal/libvmdk/blob/main/COPYING.LESSER


#### Apache-2.0

- [pytsk / pytsk3](https://github.com/py4n6/pytsk) — licensed under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).
  - Bundled version: [`pytsk3==20250801`](https://pypi.org/project/pytsk3/20250801/)
  - License text: https://github.com/py4n6/pytsk/blob/master/LICENSE
