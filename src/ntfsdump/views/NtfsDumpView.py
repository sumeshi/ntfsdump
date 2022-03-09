# coding: utf-8
import sys

from ntfsdump.models.MetaData import MetaData
from ntfsdump.views.BaseView import BaseView
from ntfsdump.presenters.NtfsDumpPresenter import NtfsDumpPresenter


class NtfsDumpView(BaseView):

    def __init__(self):
        super().__init__()
        self.define_options()
        self.args = self.parser.parse_args()

    def define_options(self):
        # If no queries have been received from the pipeline.
        if sys.stdin.isatty():
            self.parser.add_argument(
                "target_queries",
                nargs="+",
                type=str,
                help="file paths to be extracted (e.g. '/$MFT').",
            )

        self.parser.add_argument("imagefile_path", type=str, help="file path of the source image file.")
        self.parser.add_argument(
            "--volume-num",
            "-n",
            type=int,
            default=None,
            help="number of the source volume. usually, it is the system partition that is specified here (default: autodetect).",
        )
        self.parser.add_argument(
            "--output-path",
            "-o",
            type=str,
            default=".",
            help="output target directory, or file path (default: current directory \'.\' ).",
        )
        self.parser.add_argument(
            "--type",
            "-t",
            type=str,
            default='raw',
            help="format of the source image file (default: raw(dd-format))."
        )

    def run(self):
        # pipeline stdin or args
        target_queries = [i.strip() for i in sys.stdin] if not sys.stdin.isatty() else self.args.target_queries

        MetaData.quiet = self.args.quiet
        MetaData.nolog = self.args.nolog

        NtfsDumpPresenter().ntfsdump(
            imagefile_path=self.args.imagefile_path,
            output_path=self.args.output_path,
            target_queries=target_queries,
            volume_num=self.args.volume_num,
            file_type=self.args.type,
        )

def entry_point():
    NtfsDumpView().run()


if __name__ == "__main__":
    entry_point()