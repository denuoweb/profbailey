from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import build_archive
import build_hosting_site


class BuildArchiveUrlRewriteTests(unittest.TestCase):
    def test_rewrites_local_absolute_course_url_to_archive_relative_link(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "mirror"
            out = Path(temp) / "archive"
            source = root / "cs519" / "Obj" / "index.html"
            output = out / "cs519" / "Obj" / "index.html"
            source.parent.mkdir(parents=True)
            output.parent.mkdir(parents=True)

            with mock.patch.object(build_archive, "ROOT", root), mock.patch.object(build_archive, "OUT", out):
                rewritten = build_archive.rewrite_one_url(
                    "https://cs.oregonstate.edu/~mjb/cs550/",
                    source,
                    output,
                )

        self.assertEqual(rewritten, "../../cs550/index.html")

    def test_preserves_query_only_directory_index_links_as_same_page_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "mirror"
            out = Path(temp) / "archive"
            source = root / "glman" / "Examples" / "index.html"
            output = out / "glman" / "Examples" / "index.html"
            source.parent.mkdir(parents=True)
            output.parent.mkdir(parents=True)

            with mock.patch.object(build_archive, "ROOT", root), mock.patch.object(build_archive, "OUT", out):
                rewritten = build_archive.rewrite_one_url("?C=N;O=D", source, output)

        self.assertEqual(rewritten, "index.html?C=N;O=D")


class BuildHostingSelectionTests(unittest.TestCase):
    def test_hosted_paths_reuses_manifest_pages_and_includes_small_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "archive"
            archive.mkdir()
            (archive / "index.html").write_text("<!doctype html>", encoding="utf-8")
            (archive / "small.pdf").write_bytes(b"x")
            (archive / "large.bin").write_bytes(b"x" * (build_hosting_site.SMALL_FILE_LIMIT + 1))

            pages = {PurePosixPath("index.html")}
            with mock.patch.object(build_hosting_site, "ARCHIVE", archive):
                hosted = build_hosting_site.hosted_paths(pages)

        self.assertIn(PurePosixPath("index.html"), hosted)
        self.assertIn(PurePosixPath("small.pdf"), hosted)
        self.assertNotIn(PurePosixPath("large.bin"), hosted)


if __name__ == "__main__":
    unittest.main()
