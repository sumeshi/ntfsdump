# coding: utf-8
import sys
from datetime import datetime, UTC
from pathlib import Path
from typing import Literal, Optional
from traceback import format_exc

from ntfsdump.__about__ import __version__


class MetaData:
    name: str = 'ntfsdump'
    version: str = __version__
    run_time: Optional[datetime] = None
    quiet: bool = False
    no_log: bool = False


def get_datetime() -> datetime:
    return datetime.now(UTC)


def get_logfile_time() -> str:
    if not MetaData.run_time:
        MetaData.run_time = get_datetime()
    return MetaData.run_time.strftime('%Y%m%d_%H%M%S_%f')


class GlobalLogger:
    def __init__(self):
        self._log_path: Optional[Path] = None
        self._initialized: bool = False

    def _init_log_file(self):
        if self._initialized:
            return
        self._initialized = True
        
        if MetaData.no_log:
            return
            
        self._log_path = Path('.', f"{MetaData.name}_{get_logfile_time()}.log")
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
        if not self._initialized and not MetaData.no_log:
            self._init_log_file()
            
        if not MetaData.no_log:
            self._write_to_file(message)
        
        if not MetaData.quiet:
            if type == 'info':
                self.print_info(message) 
            elif type == 'danger':
                self.print_danger(message) 


_global_logger = GlobalLogger()


def get_logger() -> GlobalLogger:
    return _global_logger
