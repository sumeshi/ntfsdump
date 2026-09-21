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
- Automatically detects the input image format by signature
- Accepts a VMware VM directory, VMX or VMSD directly, without converting images
- Lists and reads VMware snapshots (`--list-snapshots`, `--snapshot`)
- Selects a virtual disk when a VM has more than one (`--list-disks`, `--disk`)
- Reads split VMDK extents and VMDK snapshot/delta chains without merging them
- Reads Hyper-V checkpoint chains (`VHDX`/`AVHDX` differencing disks) without merging or converting them
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

- Image formats: `RAW`, `E01`, `VHD`, `VHDX` (including Hyper-V `AVHDX` differencing disks), `VMDK` (auto-detected), plus VMware VM directories, VMX and VMSD
- File system: `NTFS`
- Partition tables: GPT and MBR are both supported


## Usage

### Command Line Interface

You can pass arguments directly to the CLI. The output path can be either a file path or a directory path.

```bash
ntfsdump [OPTIONS] SOURCE [PATH...]
```

`SOURCE` may be an image file, a VMware VM directory, a VMX or a VMSD:

```text
disk.raw
evidence.E01
disk.vhd
disk.vhdx
disk.avhdx
disk.vmdk
vm.vmsd
/path/to/vm/
```

**Options**:
- `--help`, `-h`: Show help message.
- `--version`, `-V`: Display program version.
- `--quiet`, `-q`: Suppress normal stdout output. Errors are still written to stderr.
- `--flat`: Extract all artifacts purely into a single folder without reconstructing directories.
- `--volume`, `-n`: Target specific NTFS volume number (default: auto-detects main OS volume).
- `--snapshot`, `-s`: Read the NTFS as it was at the given VMware snapshot. The ID is the snapshot UID shown by `--list-snapshots`. Without it, the VM's current state is read.
- `--disk`, `-d`: Read a specific VMware virtual disk by ID (default: auto-select when unique).
- `--list-snapshots`: List VMware snapshots found in the SOURCE and exit.
- `--list-disks`: List VMware virtual disks found in the SOURCE and exit.
- `--image-format`: Force the image format instead of auto-detection. Options: `raw`, `e01`, `vhd`, `vhdx`, `vmdk`.
- `--log [FILE]`: Enable logging. Optionally specify a log file path.
- `--output`, `-o`: Directory or file to save exported outputs.


#### Examples

Dump a single file (format is auto-detected):

```bash
ntfsdump -o ./dump /path/to/your/image.raw /$MFT
ntfsdump -o ./dump /path/to/your/evidence.E01 /Windows/System32/config/SYSTEM
```

Dump an entire directory recursively:

```bash
ntfsdump -o ./dump /path/to/your/image.raw /Windows/System32/winevt/Logs
```

Force the format for a file without a recognizable signature:

```bash
ntfsdump --image-format raw /path/to/your/evidence.bin /$MFT
```

#### VMware Snapshots (`--list-snapshots`, `-s/--snapshot`)

`ntfsdump` can read the NTFS volume **as it was at a specific VMware snapshot**, directly from the delta VMDK chain — without reverting the VM, cloning disks, or merging snapshots.

First, list the snapshots recorded in the VM's `VMSD` metadata:

```bash
ntfsdump ./WindowsVM --list-snapshots
ID  NAME          CREATED              PARENT
1   Initialized   2026-09-01 12:33:43  -
5   NetConnect    2026-09-02 02:25:08  1
6   PrepareTools  2026-09-10 17:46:35  5
7   SetConfigs    2026-09-25 00:51:39  5
```

- `ID` is VMware's own snapshot UID. Always take it from this listing — it is the only valid identifier.
- `PARENT` shows the snapshot lineage, so you can follow the history of the VM.

Then pass the ID with `-s` / `--snapshot` to read any point in time:

```bash
# Read the SYSTEM registry hive as it was at snapshot 5.
ntfsdump ./WindowsVM -s 5 /Windows/System32/config/SYSTEM

# Snapshot 5, second virtual disk (see disk selection below).
ntfsdump ./WindowsVM -s 5 -d 1 /Evidence
```

Notes:

- Without `-s`, the VM's **current state** is read (which may itself already be a delta chain after taking a snapshot).
- Only snapshot **IDs** are accepted; selecting by display name is not supported.
- If the VM directory has no `VMSD` (no snapshot metadata), a plain `--list-snapshots` reports `No VMware snapshot metadata was found.` rather than pretending the VMDK chain is a snapshot list.

#### Virtual Disk Selection (`--list-disks`, `-d/--disk`)

For VMs with more than one virtual disk, list them first:

```bash
ntfsdump ./WindowsVM --list-disks
ID  NODE     SIZE     VMDK
0   nvme0:0  100 GiB  Windows10_22H2(x64).vmdk
1   scsi0:1  500 GiB  Data.vmdk
```

Then select a disk with `-d` / `--disk`:

```bash
# Read the second virtual disk.
ntfsdump ./WindowsVM -d 1 /Evidence
```

- With a **single** disk, it is selected automatically.
- With **multiple** disks, `ntfsdump` refuses to guess and asks you to choose with `--list-disks` + `-d`.

#### Snapshot Delta VMDK Chains

Even a bare VMDK inside the VM directory is understood: parents are resolved automatically from the descriptors, so pointing at a delta file reads the whole chain (base + deltas) as one logical disk:

```bash
ntfsdump ./WindowsVM/Windows-000003.vmdk /$MFT
```

Using with [ntfsfind](https://github.com/sumeshi/ntfsfind) over standard input (pipe):

```bash
ntfsfind '.*\.evtx' ./image.raw | ntfsdump -o ./dump ./image.raw
```

*Note: Any absolute path (starting with `/` or `\`) passed over stdin via tools like `ntfsfind` will automatically be cleaned, and the folder hierarchy will be rebuilt faithfully inside your local output directory (`./dump/Windows/System32/winevt/Logs/System.evtx`).*

#### Hyper-V checkpoints (VHDX/AVHDX)

`ntfsdump` can read Hyper-V checkpoint (differencing disk) chains directly. Both a base `VHDX` and an `AVHDX` differencing disk are auto-detected, and either can be passed as `SOURCE`:

```bash
ntfsdump ./HyperVM/Disk_0.avhdx /$MFT
ntfsdump ./HyperVM/Disk_0.avhdx /Windows/System32/config/SYSTEM
```

- The parent chain is resolved automatically from the VHDX metadata (parent locator), so pointing at any disk in the chain reads the whole chain as one logical disk.
- Parent images are looked up next to the child image; absolute Windows parent paths are reduced to their basename.
- Images are never merged or converted — nothing is written to the source directory.
- Checkpoint listing (`--list-checkpoints`) is not yet available, and `-s` / `--snapshot` remains VMware-only.


### Python Module

You can incorporate `ntfsdump` logic into your own scripts.

```python
from ntfsdump import ntfsdump

# Image format is auto-detected. Pass image_format='raw' to force it.
ntfsdump(
    source='./path/to/your/image.raw',
    paths=['/Windows/System32/winevt/Logs'],
    output='./dump',
    volume=2,
)

# VMware VM directory, snapshot and disk selection.
ntfsdump(
    source='./WindowsVM',
    paths=['/Windows/System32/config/SYSTEM'],
    output='./dump',
    snapshot='3',
    disk=1,
)
```


## Query Syntax

`ntfsdump` uses UNIX-like path separators (`/`) for queries. Depending on the image and backend behavior, path matching may be case-sensitive.

- **File**: `/$MFT` -> extracts `$MFT`
- **ADS**: `/$Extend/$UsnJrnl:$J` -> extracts the `$J` ADS file from `$UsnJrnl`.
- **Directory**: `/Windows/System32/winevt/Logs` -> extracts all event logs recursively.
- **Prefix Expansion**: `/Windows/Prefetch/.*` -> extracts all files located in the `Prefetch` directory.


## Logs

Logging is disabled by default and no log file is created. To record which files were successfully dumped or failed, enable it explicitly:

```bash
# Auto-generated name in the current directory (e.g. ntfsdump_20260921_153000.log)
ntfsdump image.raw /$MFT --log

# Explicit log path
ntfsdump image.raw /$MFT --log ./case.log
```


## Contributing

We welcome bug reports, issues, and feature requests. Please submit them on the [GitHub repository](https://github.com/sumeshi/ntfsdump). :sushi: :sushi: :sushi:


## License

ntfsdump is released under the [MIT](LICENSE) License.


### Third-party licenses

The standalone binaries distributed via GitHub Releases bundle the following third-party libraries.


#### LGPL-3.0-or-later

The following libyal libraries are licensed under the [GNU Lesser General Public License v3.0 or later (LGPL-3.0-or-later)](https://www.gnu.org/licenses/lgpl-3.0.html).
You may obtain, modify, and rebuild them from their upstream sources in accordance with the LGPL.

- [libewf / libewf-python](https://github.com/libyal/libewf)
  - Bundled version: [`libewf-python==20240506`](https://pypi.org/project/libewf-python/20240506/) (source: https://github.com/libyal/libewf/releases/tag/20240506)
  - License text: https://github.com/libyal/libewf/blob/main/COPYING.LESSER
- [libvhdi / libvhdi-python](https://github.com/libyal/libvhdi)
  - Bundled version: [`libvhdi-python==20260901`](https://pypi.org/project/libvhdi-python/20260901/) (source: https://github.com/libyal/libvhdi/releases/tag/20260901)
  - License text: https://github.com/libyal/libvhdi/blob/main/COPYING.LESSER
- [libvmdk / libvmdk-python](https://github.com/libyal/libvmdk)
  - Bundled version: [`libvmdk-python==20260714`](https://pypi.org/project/libvmdk-python/20260714/) (source: https://github.com/libyal/libvmdk/releases/tag/20260714)
  - License text: https://github.com/libyal/libvmdk/blob/main/COPYING.LESSER


#### Apache-2.0

- [pytsk / pytsk3](https://github.com/py4n6/pytsk) — licensed under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).
  - Bundled version: [`pytsk3==20260715`](https://pypi.org/project/pytsk3/20260715/)
  - License text: https://github.com/py4n6/pytsk/blob/master/LICENSE
