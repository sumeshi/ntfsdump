# coding: utf-8
from pathlib import Path
from typing import Literal
from traceback import format_exc
from datetime import datetime

from ntfsdump.models.MetaData import MetaData


def get_datetime() -> datetime:
    return datetime.utcnow()

def get_logfile_time():
    if not MetaData.run_time:
        MetaData.run_time = get_datetime()
    return MetaData.run_time.strftime('%Y%m%d_%H%M%S_%f')


class Log(object):
    def __init__(
        self,
        path: Path = Path('.', f"{MetaData.name}_{get_logfile_time()}.log"),
    ):
        """Logging class

        Args:
            path (Path, optional): path of log file. Defaults to Path('.', f"{MetaData.name}_{get_logfile_time()}.log").
            is_quiet (bool, optional): flag to supress standard output. Defaults to False.
        """
        self.path = path
        self.is_quiet = MetaData.quiet

        if not MetaData.nolog:
            self.__create_logfile()
    
    def __create_logfile(self):
        if not self.path.exists():
            self.path.write_text(f"- {MetaData.name} v{MetaData.version} - \n")
            
    def __write_to_log(self, message: str):
        try:
            with self.path.open('a') as f:
                f.write(f"{get_datetime().isoformat()}: {message}\n")
        except Exception as e:
            self.print_danger(format_exc())

    def print_info(self, message: str):
        """print with cyan color

        Args:
            message (str): a message to be printed.
        """
        print(f"\033[36m{message}\033[0m")

    def print_danger(self, message: str):
        """print with red color

        Args:
            message (str): a message to be printed.
        """
        print(f"\033[31m{message}\033[0m")
    
    def log(self, message: str, type: Literal['system', 'info', 'danger'] = 'system'):
        """print and write message to logfile

        Args:
            message (str): a message to be logged.
            type (Literal['system', 'info', 'danger']): 'system ' is used only for logging.
        """
        if not MetaData.nolog:
            self.__write_to_log(message)
        
        if not self.is_quiet:
            if type == 'info':
                self.print_info(message) 
            elif type == 'danger':
                self.print_danger(message) 
