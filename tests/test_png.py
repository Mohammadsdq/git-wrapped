import contextlib
import io
import os
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from git_wrapped import png as pngmod
from git_wrapped.cli import main
from git_wrapped.collect import Commit
from git_wrapped.render import render_svg
from git_wrapped.stats import compute
from datetime import datetime


def fake_png(path: Path, width=pngmod.W, height=pngmod.H) -> None:
    header = pngmod.PNG_MAGIC + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height)
    path.write_bytes(header + b"\x00" * 2000)


def make_repo(tmp: str) -> Path:
    repo = Path(tmp) / "demo"
    repo.mkdir()
    git = lambda *a, **kw: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, **kw)  # noqa: E731
    git("init", "-q")
    git("config", "user.name", "Test User")
    git("config", "user.email", "test@example.com")
    (repo / "main.py").write_text("print('hi')\n")
    git("add", "-A")
    when = "2026-03-14T23:10:00+03:30"
    git("commit", "-q", "-m", "fix thing", env={**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when})
    return repo


class BackendChainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.svg = self.dir / "card.svg"
        self.svg.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_backend_gives_a_helpful_error(self):
        with self.assertRaisesRegex(pngmod.PngError, "Install one of"):
            pngmod.svg_to_png(self.svg, self.dir / "out.png", backends=[])

    def test_falls_through_to_next_backend(self):
        def broken(svg, png):
            raise pngmod.PngError("boom")

        out = self.dir / "sub" / "out.png"
        name = pngmod.svg_to_png(self.svg, out, backends=[("broken", broken), ("good", lambda s, p: fake_png(p))])
        self.assertEqual(name, "good")
        self.assertTrue(out.exists())
        self.assertEqual([p.name for p in out.parent.iterdir()], ["out.png"])  # no temp file left behind

    def test_rejects_non_png_output(self):
        junk = lambda s, p: p.write_bytes(b"not a png" * 500)  # noqa: E731
        with self.assertRaisesRegex(pngmod.PngError, "not a valid PNG"):
            pngmod.svg_to_png(self.svg, self.dir / "out.png", backends=[("junk", junk)])

    def test_rejects_wrong_size(self):
        small = lambda s, p: fake_png(p, 100, 100)  # noqa: E731
        with self.assertRaisesRegex(pngmod.PngError, "unexpected size"):
            pngmod.svg_to_png(self.svg, self.dir / "out.png", backends=[("small", small)])

    def test_failed_export_keeps_existing_png(self):
        out = self.dir / "out.png"
        out.write_bytes(b"old")
        with self.assertRaises(pngmod.PngError):
            pngmod.svg_to_png(self.svg, out, backends=[])
        self.assertEqual(out.read_bytes(), b"old")


@unittest.skipUnless(pngmod.available_backends(), "no SVG renderer installed")
class RealRenderTests(unittest.TestCase):
    def test_real_png_has_card_dimensions(self):
        commits = [Commit("demo", f"s{i}", datetime(2026, 3, 1 + i, 22, 0), "add bot", [("a.py", 5, 1)]) for i in range(12)]
        svg_text = render_svg(compute(commits, 2026), name="@me")
        with tempfile.TemporaryDirectory() as tmp:
            svg, png = Path(tmp) / "card.svg", Path(tmp) / "card.png"
            svg.write_text(svg_text, encoding="utf-8")
            pngmod.svg_to_png(svg, png)
            data = png.read_bytes()
            self.assertTrue(data.startswith(pngmod.PNG_MAGIC))
            self.assertEqual(struct.unpack(">II", data[16:24]), (pngmod.W, pngmod.H))


class CliPngTests(unittest.TestCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_png_flag_writes_svg_and_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            card = Path(tmp) / "card.svg"
            with mock.patch("git_wrapped.cli.svg_to_png", side_effect=lambda s, p: fake_png(Path(p))):
                code, out, _ = self.run_cli(str(repo), "-y", "2026", "--all-authors", "--png", "-o", str(card))
            self.assertEqual(code, 0)
            self.assertTrue(card.exists())
            self.assertTrue(card.with_suffix(".png").exists())

    def test_png_output_path_writes_only_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            card = Path(tmp) / "card.png"
            with mock.patch("git_wrapped.cli.svg_to_png", side_effect=lambda s, p: fake_png(Path(p))):
                code, _, _ = self.run_cli(str(repo), "-y", "2026", "--all-authors", "-o", str(card))
            self.assertEqual(code, 0)
            self.assertTrue(card.exists())
            self.assertFalse(card.with_suffix(".svg").exists())

    def test_failure_keeps_the_svg_and_exits_3(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            card = Path(tmp) / "card.png"
            with mock.patch("git_wrapped.cli.svg_to_png", side_effect=pngmod.PngError("no renderer")):
                code, _, err = self.run_cli(str(repo), "-y", "2026", "--all-authors", "-o", str(card))
            self.assertEqual(code, 3)
            self.assertIn("PNG export failed", err)
            self.assertTrue(card.with_suffix(".svg").exists())

    def test_plain_run_does_not_touch_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(tmp)
            card = Path(tmp) / "card.svg"
            with mock.patch("git_wrapped.cli.svg_to_png") as converter:
                code, _, _ = self.run_cli(str(repo), "-y", "2026", "--all-authors", "-o", str(card))
            self.assertEqual(code, 0)
            converter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
