# coding: utf-8
import pytsk3
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import List, Optional

from ntfsdump.errors import NtfsDumpError
from ntfsdump.logger import get_logger


logger = get_logger()

BUFF_SIZE = 1024 * 1024

# Characters that are illegal in Windows filenames. Output filenames that
# contain them (e.g. the ':' of an ADS query such as "$UsnJrnl:$J") are
# sanitized so that a dumped stream cannot become an ADS of another file
# on Windows.
_ILLEGAL_FILENAME_CHARS = '<>:"/\\|?*'


class NtfsVolume:
    def __init__(
        self,
        path: Path,
        addr: int,
        description: str,
        start_byte: int,
        end_byte: int,
        fs_info: pytsk3.FS_Info
    ):
        self.path = path
        self.addr = addr
        self.description = description
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.fs_info = fs_info

    def __clean_query(self, query: str) -> str:
        cleaned = query.replace('\\', '/')
        if not cleaned.startswith('/'):
            cleaned = '/' + cleaned
        return cleaned

    def __is_dir(self, query: str) -> bool:
        f = self.fs_info.open(query)
        return f.info.name.type == pytsk3.TSK_FS_NAME_TYPE_DIR

    def __list_artifacts(self, query: str) -> List[str]:
        results: List[str] = []
        for a in self.fs_info.open_dir(query):
            name = a.info.name.name.decode('utf-8', errors='replace')
            if name in ('.', '..'):
                continue

            # Skip deleted/unallocated name entries — these are leftovers in
            # the directory index that no longer represent a live file.
            if not (a.info.name.flags & pytsk3.TSK_FS_NAME_FLAG_ALLOC):
                logger.log(f"[skipped:deleted] {query}/{name}", 'system')
                continue

            # Skip entries whose MFT record has been reused. The name still
            # points at MFT record N, but record N now belongs to a different
            # file (different sequence number), so reading it would return
            # unrelated content (e.g. jpg/png under Prefetch).
            if a.info.meta is None:
                logger.log(f"[skipped:no-meta] {query}/{name}", 'system')
                continue
            if a.info.name.meta_seq != a.info.meta.seq:
                logger.log(
                    f"[skipped:mft-reused] {query}/{name} "
                    f"(name_seq={a.info.name.meta_seq}, meta_seq={a.info.meta.seq})",
                    'system',
                )
                continue

            results.append(name)
        return results

    def __check_output_path(self, destination_path: Path, target: Path) -> Path:
        """Ensure the extraction target never leaves the destination directory."""
        root = destination_path.resolve()
        resolved = target.resolve()
        if not resolved.is_relative_to(root):
            raise NtfsDumpError(
                f"Output path escapes the destination directory: {target}"
            )
        return target

    def __safe_filename(self, filename: str) -> str:
        """Turn "$UsnJrnl:$J" into "$UsnJrnl_$J".

        A literal ':' would make Windows treat the output file as an
        alternate data stream of the file named before it, so the stream
        name is embedded into the filename instead, keeping it identifiable.
        """
        if ':' not in filename:
            return filename
        return filename.translate(
            {ord(c): '_' for c in _ILLEGAL_FILENAME_CHARS}
        )

    def __resolve_flat_collision(
        self,
        target: Path,
        mft_entry: Optional[int],
    ) -> Path:
        """Rename a flat target so that same-name files do not overwrite
        each other (or a previously dumped file).

        The MFT entry number is used as the discriminating suffix.
        """
        if not target.exists():
            return target

        stem = target.stem
        suffix = target.suffix

        if mft_entry is not None:
            candidate = target.with_name(f"{stem}_{mft_entry}{suffix}")
            if not candidate.exists():
                return candidate

        counter = 1
        while True:
            candidate = target.with_name(f"{stem}_{counter}{suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    def __read_file(self, query: str) -> bytes:
        """Return the complete content of a file as bytes.

        Kept as a full-bytes API (e.g. ntfsfind reads $MFT through this);
        a premature EOF is reported as an error instead of returning a
        truncated buffer.
        """
        f = self.fs_info.open(query)

        offset = 0
        size = f.info.meta.size

        result = bytearray()

        while offset < size:
            available_to_read = min(BUFF_SIZE, size - offset)
            data = f.read_random(offset, available_to_read)
            if not data:
                break

            offset += len(data)
            result.extend(data)

        if offset < size:
            raise NtfsDumpError(
                f"Unexpected EOF while reading {query}: "
                f"read {offset} of {size} bytes."
            )

        return bytes(result)

    def __find_ads_attribute(self, f, ads: str):
        for attribute in f:
            if attribute.info.name == ads.encode('utf-8'):
                return attribute
        return None

    def __write_stream(
        self,
        f,
        destination_path: Path,
        size: int,
        ads_attribute=None,
    ) -> None:
        """Read the stream in chunks and replace the destination on success.

        Extraction memory does not grow with the file size. If the stream
        fails, only the temporary output is removed; an existing destination
        is preserved. Successful extraction replaces an existing file.
        """
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        if destination_path.is_dir():
            raise IsADirectoryError(f"Destination path is an existing directory: {destination_path}")

        out = NamedTemporaryFile(
            mode='wb', dir=destination_path.parent, prefix='.ntfsdump-', delete=False,
        )
        temporary_path = Path(out.name)
        try:
            with out:
                offset = 0
                while offset < size:
                    available_to_read = min(BUFF_SIZE, size - offset)
                    if ads_attribute is None:
                        data = f.read_random(offset, available_to_read)
                    else:
                        data = f.read_random(
                            offset,
                            available_to_read,
                            ads_attribute.info.type,
                            ads_attribute.info.id,
                        )
                    if not data:
                        raise NtfsDumpError(
                            f"Unexpected EOF while reading {destination_path}: "
                            f"read {offset} of {size} bytes."
                        )
                    out.write(data)
                    offset += len(data)
            temporary_path.replace(destination_path)
        finally:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    def dump_files(self, query: str, destination_path: Path, flat: bool = False) -> None:
        query = self.__clean_query(query)
        logger.log(f"[query] {query}", 'system')

        if query.endswith('.*'):
            # Wildcard expansion (documented as "prefix expansion", e.g.
            # /Windows/Prefetch/.*). Checked first: pytsk3 cannot open the
            # literal ".*" path, so the dir/file checks below would fail.
            base_query = query.replace('.*', '')
            parent_dir = str(Path(base_query).parent).replace('\\', '/')
            file_prefix = Path(base_query).name

            files = [
                artifact for artifact in self.__list_artifacts(parent_dir)
                if artifact.startswith(file_prefix)
            ]
            for file in files:
                newquery = str(Path(parent_dir) / file)
                self.dump_files(query=newquery, destination_path=destination_path, flat=flat)
            return

        try:
            is_dir = self.__is_dir(query)
        except Exception as e:
            raise NtfsDumpError(
                f"Query path was not found in the NTFS volume: {query} ({e})"
            ) from e

        if is_dir:
            for artifact in self.__list_artifacts(query):
                newquery = str(Path(query) / artifact)
                # recursive dump
                self.dump_files(query=newquery, destination_path=destination_path, flat=flat)
        else:
            # A regular file, or an exotic entry that is still openable:
            # a failure is reported to the caller instead of being swallowed.
            self.__dump_file(self.fs_info.open(query), query, destination_path, flat)

    def __dump_file(self, f, query: str, destination_path: Path, flat: bool) -> None:
        meta = f.info.meta
        if meta is None:
            # An entry without MFT metadata cannot be read reliably; never
            # report an empty (or partial) file as a successful extraction.
            raise NtfsDumpError(
                f"MFT metadata was not found for the query: {query}"
            )
        mft_entry = meta.addr
        filename = Path(query).name

        # Alternate Data Stream
        if ':' in filename:
            _, ads_name = query.split(':', 1)
            ads_attribute = self.__find_ads_attribute(f, ads_name)
            if ads_attribute is None:
                raise NtfsDumpError(
                    f"Alternate data stream was not found: {query}"
                )
            size = ads_attribute.info.size
        else:
            ads_attribute = None
            size = meta.size

        output_name = self.__safe_filename(filename)

        # Flat mode joins the whole directory path into the filename
        # (e.g. "/Windows/System32/cmd.exe" -> "Windows_System32_cmd.exe")
        # so that same-name files from different directories stay apart.
        q_path = Path(query.lstrip('/'))
        flat_name = self.__safe_filename('_'.join(q_path.parts))

        if destination_path.name in (filename, output_name, flat_name):
            target = self.__check_output_path(destination_path, destination_path)
        else:
            if flat:
                target = destination_path / flat_name
            else:
                # Always recreate the directory tree using relative path
                target = destination_path / q_path.parent / output_name
            target = self.__check_output_path(destination_path, target)
            if flat:
                target = self.__resolve_flat_collision(target, mft_entry)

        try:
            self.__write_stream(f, target, size, ads_attribute)

        except IsADirectoryError:
            if target != destination_path:
                # The reconstructed tree target is occupied by a directory
                # (e.g. leftovers of a previous partial extraction); never
                # silently move the output somewhere else.
                raise NtfsDumpError(
                    f"Destination path is an existing directory: {target}"
                ) from None
            # ``-o`` pointed at an existing directory: write the named
            # file into it instead.
            target = destination_path / (flat_name if flat else output_name)
            if flat:
                target = self.__resolve_flat_collision(target, mft_entry)
            self.__write_stream(f, target, size, ads_attribute)

        logger.log(f"[dumped] {target}", 'info')
