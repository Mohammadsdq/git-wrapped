import itertools
import os
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

from git_wrapped.collect import Commit, clean_path, collect
from git_wrapped.render import render_svg
from git_wrapped.stats import compute, heat_level, longest_streak
from git_wrapped.terminal import render_terminal

_ids = itertools.count()


def mk(when, subject="fix bug", files=None, repo="demo"):
    return Commit(repo, f"sha{next(_ids)}", datetime.fromisoformat(when), subject,
                  files if files is not None else [("a.py", 10, 2)])


class StatsTests(unittest.TestCase):
    def test_longest_streak(self):
        days = [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 10)]
        self.assertEqual(longest_streak(days), (3, date(2026, 1, 1), date(2026, 1, 3)))

    def test_heat_level_bounds(self):
        self.assertEqual(heat_level(0, 10), 0)
        self.assertEqual(heat_level(1, 10), 1)
        self.assertEqual(heat_level(10, 10), 4)

    def test_night_owl_persona(self):
        commits = [mk(f"2026-03-{d:02d}T23:15:00") for d in range(1, 13)]
        s = compute(commits, 2026)
        self.assertEqual(s.persona.title, "Night Owl")
        self.assertEqual(s.hours[23], 12)

    def test_lock_files_and_minified_are_ignored(self):
        files = [("app.py", 10, 0), ("package-lock.json", 1000, 0), ("x.min.js", 50, 0)]
        s = compute([mk("2026-05-01T10:00:00", files=files)], 2026)
        self.assertEqual(s.lines_added, 10)
        self.assertEqual(s.languages, [("Python", 10)])

    def test_fix_count_and_top_word(self):
        commits = [mk("2026-05-01T10:00:00", "fix telegram bot"), mk("2026-05-02T10:00:00", "telegram polling")]
        s = compute(commits, 2026)
        self.assertEqual(s.fix_commits, 1)
        self.assertEqual(s.top_word, ("telegram", 2))


class CollectTests(unittest.TestCase):
    def test_clean_path(self):
        self.assertEqual(clean_path("src/{old => new}/x.py"), "src/new/x.py")
        self.assertEqual(clean_path("a.py => b.py"), "b.py")
        self.assertEqual(clean_path("plain.py"), "plain.py")

    def test_end_to_end_with_real_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "demo"
            repo.mkdir()
            git = lambda *a, **kw: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, **kw)  # noqa: E731
            git("init", "-q")
            git("config", "user.name", "Test User")
            git("config", "user.email", "test@example.com")
            for i, when in enumerate(["2026-03-14T23:10:00+03:30", "2026-03-15T09:00:00+03:30", "2025-12-31T12:00:00+03:30"]):
                (repo / "main.py").write_text("\n".join(f"line {n}" for n in range(i + 3)) + "\n")
                git("add", "-A")
                env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
                git("commit", "-q", "-m", f"fix thing {i}", env=env)

            repos, commits = collect(tmp, 2026, ["test@example.com"])
            self.assertEqual(len(repos), 1)
            self.assertEqual(len(commits), 2)  # the 2025 commit is excluded
            self.assertEqual(commits[0].when, datetime(2026, 3, 14, 23, 10))  # author-local time kept
            self.assertTrue(all(c.files for c in commits))

            _, nobody = collect(tmp, 2026, ["someone-else@example.com"])
            self.assertEqual(nobody, [])


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.stats = compute(
            [mk(f"2026-{m:02d}-{d:02d}T{h:02d}:00:00", "add <b>&bot") for m in (1, 2, 3) for d in (1, 2, 3) for h in (9, 22)],
            2026,
        )

    def test_svg_is_valid_xml_and_escapes(self):
        svg = render_svg(self.stats, name="@me & you")
        root = ET.fromstring(svg)  # raises on invalid XML
        self.assertTrue(root.tag.endswith("svg"))
        self.assertIn("@me &amp; you", svg)

    def test_svg_has_one_cell_per_day(self):
        svg = render_svg(self.stats)
        self.assertEqual(svg.count("<title>") - 25, 365)  # 1 doc title + 24 hour bars are the other titles

    def test_terminal_plain_has_no_escape_codes(self):
        self.assertNotIn("\x1b", render_terminal(self.stats, color=False))

    def test_terminal_colour_has_escape_codes(self):
        self.assertIn("\x1b[", render_terminal(self.stats, color=True))


if __name__ == "__main__":
    unittest.main()
