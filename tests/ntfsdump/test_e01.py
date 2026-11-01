from types import SimpleNamespace

import pytest

from ntfsdump.errors import NtfsDumpError
from ntfsdump.formats.e01 import E01Handler
from ntfsdump.image_paths import ensure_distinct_output


def test_all_ewf_segments_are_protected(tmp_path, monkeypatch):
    segments = [tmp_path / 'image.E01', tmp_path / 'image.E02']
    for path in segments:
        path.write_bytes(b'evidence')
    opened = []
    handle = SimpleNamespace(
        open=lambda paths, mode: opened.extend(paths),
        close=lambda: None,
        get_media_size=lambda: 8192,
    )
    monkeypatch.setattr('ntfsdump.formats.e01.pyewf.glob', lambda path: list(map(str, segments)))
    monkeypatch.setattr('ntfsdump.formats.e01.pyewf.handle', lambda: handle)

    image = E01Handler().get_img_info(str(segments[0]))
    try:
        assert opened == list(map(str, segments))
        for path in segments:
            with pytest.raises(NtfsDumpError, match='overwrite an input image'):
                ensure_distinct_output(path, image.source_paths)
            assert path.read_bytes() == b'evidence'
    finally:
        image.close()
