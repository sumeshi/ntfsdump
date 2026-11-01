# coding: utf-8
import os
import sys
from datetime import datetime, UTC
from pathlib import Path
from typing import Iterable, Literal, Optional, TextIO
from traceback import format_exc

from ntfsdump.__about__ import __version__
from ntfsdump.errors import NtfsDumpError
from ntfsdump.image_paths import ensure_distinct_output

AUTO_LOG = ""


class MetaData:
    name: str = "ntfsdump"
    version: str = __version__
    run_time: Optional[datetime] = None
    quiet: bool = False
    log_path: Optional[Path] = None
    source_paths: tuple[Path, ...] = ()
    source_file_ids: frozenset[tuple[int, int]] = frozenset()


def protect_source_paths(paths: Iterable[Path]) -> None:
    """Register all opened inputs before logging can write to a destination."""
    MetaData.source_paths = tuple(paths)
    identities = set()
    for path in MetaData.source_paths:
        info = path.stat()
        identities.add((info.st_dev, info.st_ino))
    MetaData.source_file_ids = frozenset(identities)


def get_datetime() -> datetime:
    return datetime.now(UTC)


def get_logfile_time() -> str:
    if not MetaData.run_time:
        # Use local time so the auto-generated filename is intuitive.
        MetaData.run_time = datetime.now()
    return MetaData.run_time.strftime("%Y%m%d_%H%M%S")


class GlobalLogger:
    def __init__(self):
        self._log_path: Optional[Path] = None
        self._initialized: bool = False
        self._output_collision: bool = False

    def reset(self):
        self._log_path = None
        self._initialized = False
        self._output_collision = False

    def _init_log_file(self):
        if self._initialized:
            return

        if MetaData.log_path is None:
            self._initialized = True
            return

        self._log_path = Path(MetaData.log_path)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        # Append mode never truncates a pre-existing image, even if a symlink
        # changes between validation and opening the destination.
        with self._log_path.open("a", encoding="utf-8") as log_file:
            self._validate_log_file(log_file)
            if os.fstat(log_file.fileno()).st_size == 0:
                log_file.write(f"- {MetaData.name} v{MetaData.version} -\n")
        self._initialized = True

    def _validate_log_file(self, log_file: TextIO) -> None:
        assert self._log_path is not None
        ensure_distinct_output(self._log_path, MetaData.source_paths)
        info = os.fstat(log_file.fileno())
        if (info.st_dev, info.st_ino) in MetaData.source_file_ids:
            raise NtfsDumpError(
                f"Log output would overwrite an input image file: {self._log_path}"
            )

    def ensure_not_output(self, output: Path) -> None:
        """Reject a log path that aliases an extracted file before writing either."""
        log_path = self._log_path or MetaData.log_path
        if log_path is None:
            return
        log_path = Path(log_path)
        output = Path(output)
        same_file = log_path.resolve() == output.resolve()
        if not same_file:
            try:
                same_file = log_path.samefile(output)
            except FileNotFoundError:
                pass
        if same_file:
            self._output_collision = True
            raise NtfsDumpError(
                f"Log output would overwrite an extracted file: {log_path}"
            )

    def _write_to_file(self, message: str):
        if not self._log_path:
            return
        try:
            with self._log_path.open("a", encoding="utf-8") as f:
                self._validate_log_file(f)
                f.write(f"{get_datetime().isoformat()}: {message}\n")
        except NtfsDumpError:
            raise
        except Exception:
            self.print_danger(format_exc())

    def print_info(self, message: str):
        print(f"\033[36m{message}\033[0m")

    def print_danger(self, message: str):
        print(f"\033[31m{message}\033[0m", file=sys.stderr)

    def log(self, message: str, type: Literal["system", "info", "danger"] = "system"):
        if not self._initialized:
            self._init_log_file()

        if self._log_path:
            self._write_to_file(message)

        if type == "danger":
            self.print_danger(message)
        elif not MetaData.quiet:
            self.print_info(message)

    def log_failure(self, message: str) -> None:
        """Persist a CLI failure without changing its stderr behavior or recursing."""
        # The logger becomes initialized only after its first normal log call,
        # which follows ImageFile's source-path registration. Never initialize
        # it from an early CLI failure handler: source resolution may have
        # failed before the complete input/backing-file set was known.
        if MetaData.log_path is None or self._output_collision or not self._initialized:
            return
        try:
            self._write_to_file(f"[error] {message}")
        except Exception:
            # The original CLI error remains authoritative if logging itself fails.
            pass


_global_logger = GlobalLogger()


def configure_logging(log: Optional[str]) -> None:
    """Configure opt-in logging.

    ``log`` semantics:
        * ``None``: logging disabled (default).
        * ``AUTO_LOG`` (empty string): auto-generated filename.
        * any other string: explicit log file path.
    """
    _global_logger.reset()
    MetaData.run_time = None
    MetaData.source_paths = ()
    MetaData.source_file_ids = frozenset()
    if log is None:
        MetaData.log_path = None
    elif log == AUTO_LOG:
        MetaData.log_path = Path(f"{MetaData.name}_{get_logfile_time()}.log")
    else:
        MetaData.log_path = Path(log)


def get_logger() -> GlobalLogger:
    return _global_logger
