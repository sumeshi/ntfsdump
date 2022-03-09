# coding: utf-8
import argparse
from abc import ABCMeta, abstractmethod

from ntfsdump.models.MetaData import MetaData


class BaseView(metaclass=ABCMeta):

    def __init__(self):
        self.parser = argparse.ArgumentParser()
        self.__define_common_options()

    def __define_common_options(self):
        self.parser.add_argument("--version", "-v", action="version", version=MetaData.version)
        self.parser.add_argument("--quiet", "-q", action='store_true', help="flag to suppress standard output.")
        self.parser.add_argument("--nolog", action='store_true', help="flag to no logs are output.")

    @abstractmethod
    def define_options(self):
        pass
