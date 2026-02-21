# coding: utf-8
import argparse
import sys

from ntfsdump.core import ntfsdump
from ntfsdump.logger import MetaData


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="An efficient tool for extracting files directly from NTFS image files."
    )
    
    # Optional arguments
    parser.add_argument(
        "--version", "-V", action="version", version=MetaData.version
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="suppress standard output."
    )
    parser.add_argument(
        "--no-log", action="store_true", help="prevent log file creation."
    )
    parser.add_argument(
        "--flat", action="store_true", help="save files flatly instead of reconstructing the tree (default: False)."
    )
    parser.add_argument(
        "--output", "-o", type=str, default=".",
        help="output destination directory or file path (default: current dir '.')."
    )
    parser.add_argument(
        "--format", "-f", type=str, default="raw",
        help="format of the disk image (default: 'raw'). supported: raw, e01, vhd, vhdx, vmdk."
    )
    parser.add_argument(
        "--volume", "-n", type=int, default=None,
        help="target NTFS volume number (default: auto-detect system volume)."
    )

    # Positional arguments
    parser.add_argument(
        "image", type=str, help="path to the target disk image file."
    )
    
    if sys.stdin.isatty():
        parser.add_argument(
            "paths",
            nargs="+",
            type=str,
            help="internal NTFS file or directory paths to extract (e.g. '/$MFT')."
        )
    else:
        parser.add_argument(
            "paths",
            nargs="*",
            type=str,
            help="internal NTFS file or directory paths to extract (optional if provided via stdin)."
        )

    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()

    # Read from stdin if piped
    if not sys.stdin.isatty() and not args.paths:
        paths = [line.strip() for line in sys.stdin if line.strip()]
    elif not sys.stdin.isatty() and args.paths:
        # Both stdin and purely positional are mixed
        paths = args.paths + [line.strip() for line in sys.stdin if line.strip()]
    else:
        paths = args.paths

    MetaData.quiet = args.quiet
    MetaData.no_log = args.no_log

    ntfsdump(
        image=args.image,
        paths=paths,
        output=args.output,
        volume=args.volume,
        format=args.format,
        flat=args.flat,
    )

if __name__ == "__main__":
    main()
