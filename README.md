# ntfsdump

[![LGPLv3+ License](http://img.shields.io/badge/license-LGPLv3+-blue.svg?style=flat)](LICENSE)
[![PyPI version](https://badge.fury.io/py/ntfsdump.svg)](https://badge.fury.io/py/ntfsdump)
[![Python Versions](https://img.shields.io/pypi/pyversions/ntfsdump.svg)](https://pypi.org/project/ntfsdump/)
[![pytest](https://github.com/sumeshi/ntfsdump/actions/workflows/test.yaml/badge.svg)](https://github.com/sumeshi/ntfsdump/actions/workflows/test.yaml)

![ntfsdump logo](https://gist.githubusercontent.com/sumeshi/c2f430d352ae763273faadf9616a29e5/raw/baa85b045e0043914218cf9c0e1d1722e1e7524b/ntfsdump.svg)

An efficient tool for extracting files, directories, and alternate data streams directly from NTFS image files.

## 🚀 Overview

`ntfsdump` allows digital forensic investigators and incident responders to seamlessly extract records from disk images without needing to mount them. By leveraging powerful backend libraries like `pytsk3` and `libyal`, it supports reading from standard disk image formats (RAW, E01, VHD(x), VMDK) and reliably dumps NTFS structures.

## 📦 Features

- **Direct Extraction**: Avoid mounting overhead by extracting files directly from NTFS partitions.
- **Support Multiple Formats**: Read from `.raw`, `.e01`, `.vhd`, `.vhdx`, and `.vmdk`.
- **Recursive Directory Dumping**: Extract entire folders seamlessly.
- **Alternate Data Stream (ADS)**: Supports extracting hidden alternate data streams.
- **Glob & Wildcard Queries**: Basic support for extracting matched artifacts (e.g. `.*`).
- **Use as a CLI or Python Module**: Highly flexible to integrate into other automated tools.

## ⚙️ Execution Environment

- **Python**: Compatible with Python 3.13+.
- **Precompiled Binaries**: Available for both Windows and Linux in the [GitHub releases](https://github.com/sumeshi/ntfsdump/releases) section.


## 📂 Installation

```bash
# From PyPI
pip install ntfsdump

# Form GitHub Releases (Precompiled Binaries)
chmod +x ./ntfsdump
./ntfsdump --help
```

## 🛠️ Requirements & File Prerequisites

The image file must meet the following conditions:
- **Formats**: `raw`, `e01`, `vhd`, `vhdx`, `vmdk`.
- **File System**: `NTFS`.
- **Partition Table**: `GPT` (MBR will usually be auto-detected, but GPT is officially supported).


## 💻 Usage

### Command Line Interface

You can pass arguments directly into the CLI. Output paths can be either file paths or directory paths.

```bash
ntfsdump [OPTIONS] <IMAGE> [PATHS...]
```

**Options**:
- `--help`, `-h`: Show help message.
- `--version`, `-V`: Display program version.
- `--quiet`, `-q`: Suppress stdout output.
- `--no-log`: Prevent log file creation.
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

Extracting from split E01 images (Provide the starting segment `.E01`):
```bash
ntfsdump --format=e01 -o ./dump ./path/to/your/image.E01 /Windows/System32/winevt/Logs
```

Using with [ntfsfind](https://github.com/sumeshi/ntfsfind) over standard input (pipe):
```bash
ntfsfind '.*\.evtx' ./image.raw | ntfsdump ./image.raw
```

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

## 🔍 Query Syntax

**`ntfsdump` utilizes UNIX-like path separators (`/`) for queries.** Paths are case-sensitive relative to the target volume structure.
- **File**: `/$MFT` -> extracts `$MFT`
- **ADS**: `/$Extend/$UsnJrnl:$J` -> extracts the `$J` ADS file from `$UsnJrnl`.
- **Directory**: `/Windows/System32/winevt/Logs` -> extracts all event logs recursively.
- **Prefix Expansion**: `/Windows/Prefetch/.*` -> extracts all files located in the `Prefetch` dir.

## 📝 Logs

By default, an execution log (e.g. `ntfsdump_20240101_153205_1234.log`) is generated in the current directory to safely record which files were successfully dumped or failed.
*To disable logging entirely, append the `--no-log` flag.*

## 🤝 Contributing

We welcome reports, issues, and feature requests. Please do so on the [GitHub repository](https://github.com/sumeshi/ntfsdump). :sushi: :sushi: :sushi:

## 📜 License

Released under the [LGPLv3+](LICENSE) License.

Powered by:
- [pytsk](https://github.com/py4n6/pytsk)
- [libewf](https://github.com/libyal/libewf)
- [libvhdi](https://github.com/libyal/libvhdi)
- [libvmdk](https://github.com/libyal/libvmdk)
