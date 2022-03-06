# coding: utf-8
import sys

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
                help="Target File Windows Path (ex. /Users/user/Desktop/target.txt).",
            )

        self.parser.add_argument("imagefile_path", type=str, help="raw image file")
        self.parser.add_argument(
            "--volume-num",
            "-n",
            type=int,
            default=None,
            help="NTFS volume number(default: autodetect).",
        )
        self.parser.add_argument(
            "--output-path",
            "-o",
            type=str,
            default=".",
            help="Output directory or file path(default: current directory \'.\' ).",
        )

    def run(self):
        # pipeline stdin or args
        target_queries = [i.strip() for i in sys.stdin] if not sys.stdin.isatty() else self.args.target_queries

        NtfsDumpPresenter.ntfsdump(
            imagefile_path=self.args.imagefile_path,
            output_path=self.args.output_path,
            target_queries=target_queries,
            volume_num=self.args.volume_num
        )

def entry_point():
    NtfsDumpView().run()


if __name__ == "__main__":
    entry_point()