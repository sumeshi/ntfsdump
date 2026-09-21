# coding: utf-8
import argparse
import os
import sys
from typing import Iterable, List, Optional, Sequence
from traceback import format_exc

from ntfsdump.core import ntfsdump
from ntfsdump.errors import NtfsDumpError
from ntfsdump.formats import VALID_IMAGE_FORMATS
from ntfsdump.formats.vmdk import probe_media_size
from ntfsdump.logger import AUTO_LOG, MetaData, configure_logging
from ntfsdump.sources import SourceResolver, VmwareSource
from ntfsdump.vmware import (
    NO_DISKS_MESSAGE,
    NO_SNAPSHOT_METADATA_MESSAGE,
)


_EPILOG = """\
examples:
  ntfsdump evidence.E01 /Windows/System32/config/SYSTEM
      extract files from an image (format is auto-detected).

  ntfsdump ./WindowsVM --list-snapshots
      list VMware snapshots (ID/NAME/CREATED/PARENT). Use an ID with -s.

  ntfsdump ./WindowsVM -s 5 /Windows/System32/config/SYSTEM
      read the NTFS as it was at snapshot 5, directly from the delta chain.

  ntfsdump ./WindowsVM --list-disks
      list virtual disks (ID/NODE/SIZE/VMDK). Use an ID with -d.

  ntfsdump ./WindowsVM -s 5 -d 1 /Evidence
      combine snapshot and disk selection.

  ntfsdump image.raw /$MFT --log ./case.log
      enable logging to an explicit file (logging is disabled by default).
"""


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='ntfsdump',
        description=(
            "An efficient tool for extracting files directly from NTFS images "
            "and VMware VM directories without mounting them."
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Optional arguments
    parser.add_argument(
        "--version", "-V", action="version", version=MetaData.version
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="suppress standard output. Errors are still written to stderr."
    )
    parser.add_argument(
        "--flat", action="store_true",
        help="save files flatly instead of reconstructing the tree (default: False)."
    )
    parser.add_argument(
        "--output", "-o", type=str, default=".",
        help="output destination directory or file path (default: current dir '.')."
    )
    parser.add_argument(
        "--volume", "-n", type=int, default=None,
        help="target NTFS volume number (default: auto-detect main OS volume)."
    )
    parser.add_argument(
        "--snapshot", "-s", type=str, default=None,
        help=(
            "VMware snapshot UID to read, as shown by --list-snapshots. "
            "Reads the NTFS as it was at that point in time, directly from the "
            "delta chain (default: current VM state)."
        )
    )
    parser.add_argument(
        "--disk", "-d", type=int, default=None,
        help=(
            "VMware virtual disk ID to read, as shown by --list-disks. "
            "With a single disk it is selected automatically; with multiple "
            "disks this option is required."
        )
    )
    parser.add_argument(
        "--list-snapshots", action="store_true",
        help=(
            "list VMware snapshots (ID/NAME/CREATED/PARENT) found in the "
            "SOURCE and exit. Pass an ID to --snapshot/-s to read that state."
        )
    )
    parser.add_argument(
        "--list-disks", action="store_true",
        help=(
            "list VMware virtual disks (ID/NODE/SIZE/VMDK) found in the "
            "SOURCE and exit. Pass an ID to --disk/-d to read that disk."
        )
    )
    parser.add_argument(
        "--image-format", type=str, default=None, choices=list(VALID_IMAGE_FORMATS),
        help="force the input image format instead of auto-detection."
    )
    parser.add_argument(
        "--log", nargs='?', const=AUTO_LOG, default=None, metavar='FILE',
        help=(
            "enable logging, which is disabled by default. Optionally specify "
            "a log file path (default: auto-generated name)."
        )
    )

    # Positional arguments
    parser.add_argument(
        "source", type=str,
        help="disk image file, VMware VM directory, VMX or VMSD path."
    )
    parser.add_argument(
        "paths", nargs='*', type=str,
        help="internal NTFS file or directory paths to extract (e.g. '/$MFT')."
    )

    return parser


def _collect_paths(args) -> List[str]:
    paths = list(args.paths)
    if paths:
        return paths
    if sys.stdin is not None and not sys.stdin.isatty():
        try:
            paths += [line.strip() for line in sys.stdin if line.strip()]
        except (OSError, ValueError):
            pass
    return paths


def _print_table(rows: Sequence[Sequence[str]]) -> None:
    if not rows:
        return
    widths = [max(len(str(row[i])) for row in rows) for i in range(len(rows[0]))]
    for row in rows:
        line = '  '.join(
            str(cell).ljust(widths[i]) for i, cell in enumerate(row)
        )
        print(line.rstrip())


def _format_size(size: Optional[int]) -> str:
    if size is None:
        return '-'
    for label, factor in (
        ('TiB', 1 << 40),
        ('GiB', 1 << 30),
        ('MiB', 1 << 20),
        ('KiB', 1 << 10),
    ):
        if size >= factor:
            value = size / factor
            if value == int(value):
                return f"{int(value)} {label}"
            return f"{value:.1f} {label}"
    return f"{size} B"


def _require_vmware_source(resolved, message: str) -> VmwareSource:
    if not isinstance(resolved, VmwareSource):
        raise NtfsDumpError(message)
    return resolved


def _print_snapshots(resolved) -> None:
    source = _require_vmware_source(resolved, NO_SNAPSHOT_METADATA_MESSAGE)
    snapshots = source.snapshots
    if not snapshots:
        raise NtfsDumpError(NO_SNAPSHOT_METADATA_MESSAGE)

    rows: List[Sequence[str]] = [('ID', 'NAME', 'CREATED', 'PARENT')]
    for snapshot in snapshots:
        created = (
            snapshot.created_at.strftime('%Y-%m-%d %H:%M:%S')
            if snapshot.created_at else '-'
        )
        rows.append((
            str(snapshot.id),
            snapshot.name or '-',
            created,
            str(snapshot.parent_id) if snapshot.parent_id else '-',
        ))
    _print_table(rows)


def _print_disks(resolved) -> None:
    source = _require_vmware_source(resolved, NO_DISKS_MESSAGE)
    disks = source.disks
    if not disks:
        raise NtfsDumpError(NO_DISKS_MESSAGE)

    rows: List[Sequence[str]] = [('ID', 'NODE', 'SIZE', 'VMDK')]
    for disk in disks:
        size = disk.size if disk.size is not None else probe_media_size(disk.path)
        rows.append((
            str(disk.id),
            disk.node,
            _format_size(size),
            disk.path.name,
        ))
    _print_table(rows)


def _run(args) -> None:
    resolved = SourceResolver().resolve(
        args.source,
        image_format=args.image_format,
        snapshot=args.snapshot,
        disk=args.disk,
    )

    if args.list_snapshots:
        _print_snapshots(resolved)
        return
    if args.list_disks:
        _print_disks(resolved)
        return

    paths = _collect_paths(args)
    if not paths:
        raise NtfsDumpError("No path was given to extract.")

    ntfsdump(
        source=args.source,
        paths=paths,
        output=args.output,
        volume=args.volume,
        image_format=args.image_format,
        snapshot=args.snapshot,
        disk=args.disk,
        flat=args.flat,
    )


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)

    MetaData.quiet = args.quiet
    configure_logging(args.log)

    try:
        _run(args)
    except NtfsDumpError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        # Convert unexpected backend errors into a clear CLI message instead of
        # dumping a Python traceback for user input problems.
        # Set NTFSDUMP_DEBUG=1 to print the full traceback for troubleshooting.
        print(str(exc) or exc.__class__.__name__, file=sys.stderr)
        if os.environ.get('NTFSDUMP_DEBUG'):
            print(format_exc(), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
