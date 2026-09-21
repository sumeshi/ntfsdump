# coding: utf-8
import sys
from datetime import datetime, UTC
from pathlib import Path
from typing import Literal, Optional
from traceback import format_exc

from ntfsdump.__about__ import __version__


AUTO_LOG = ''


class MetaData:
    name: str = 'ntfsdump'
    version: str = __version__
    run_time: Optional[datetime] = None
    quiet: bool = False
    log_path: Optional[Path] = None


def get_datetime() -> datetime:
    return datetime.now(UTC)


def get_logfile_time() -> str:
    if not MetaData.run_time:
        # Use local time so the auto-generated filename is intuitive.
        MetaData.run_time = datetime.now()
    return MetaData.run_time.strftime('%Y%m%d_%H%M%S')


class GlobalLogger:
    def __init__(self):
        self._log_path: Optional[Path] = None
        self._initialized: bool = False

    def reset(self):
        self._log_path = None
        self._initialized = False

    def _init_log_file(self):
        if self._initialized:
            return
        self._initialized = True

        if MetaData.log_path is None:
            return

        self._log_path = Path(MetaData.log_path)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._log_path.exists():
            self._log_path.write_text(f"- {MetaData.name} v{MetaData.version} -\n")

    def _write_to_file(self, message: str):
        if not self._log_path:
            return
        try:
            with self._log_path.open('a') as f:
                f.write(f"{get_datetime().isoformat()}: {message}\n")
        except Exception:
            self.print_danger(format_exc())

    def print_info(self, message: str):
        print(f"\033[36m{message}\033[0m")

    def print_danger(self, message: str):
        print(f"\033[31m{message}\033[0m", file=sys.stderr)

    def log(self, message: str, type: Literal['system', 'info', 'danger'] = 'system'):
        if not self._initialized:
            self._init_log_file()

        if self._log_path:
            self._write_to_file(message)

        if type == 'danger':
            self.print_danger(message)
        elif not MetaData.quiet:
            self.print_info(message)


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
    if log is None:
        MetaData.log_path = None
    elif log == AUTO_LOG:
        MetaData.log_path = Path(f"{MetaData.name}_{get_logfile_time()}.log")
    else:
        MetaData.log_path = Path(log)


def get_logger() -> GlobalLogger:
    return _global_logger
