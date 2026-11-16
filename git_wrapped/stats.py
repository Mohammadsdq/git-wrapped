"""Turn a list of commits into the numbers that go on the card."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import PurePosixPath

LANG_BY_EXT = {
    ".py": "Python", ".pyw": "Python", ".ipynb": "Jupyter",
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".lua": "Lua", ".go": "Go", ".rs": "Rust", ".java": "Java", ".kt": "Kotlin",
    ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".hpp": "C++", ".cs": "C#",
    ".php": "PHP", ".rb": "Ruby", ".swift": "Swift", ".dart": "Dart",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell",
    ".html": "HTML", ".css": "CSS", ".scss": "CSS", ".vue": "Vue", ".svelte": "Svelte",
    ".sql": "SQL", ".md": "Markdown",
}
NOISE_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "cargo.lock", "composer.lock", "gemfile.lock", "go.sum",
}
NOISE_DIRS = {"node_modules", "vendor", "dist", "build", "__pycache__", ".venv", "venv"}
NOISE_SUFFIXES = (".lock", ".min.js", ".min.css", ".map")

STOP_WORDS = {
    "the", "and", "for", "with", "from", "into", "this", "that", "add", "adds", "added", "update",
    "updated", "updates", "merge", "branch", "remove", "removed", "change", "changes", "changed",
    "use", "using", "file", "files", "code", "new", "make", "get", "set", "via", "its", "are",
    "was", "not", "you", "all", "one", "some", "more", "fix", "fixes", "fixed", "wip", "initial", "commit",
}
WORD_RE = re.compile(r"[a-z][a-z']{2,}")
FIX_RE = re.compile(r"\bfix")


def is_noise(path: str) -> bool:
    p = PurePosixPath(path)
    name = p.name.lower()
    if name in NOISE_NAMES or name.endswith(NOISE_SUFFIXES):
        return True
    return any(part in NOISE_DIRS for part in p.parts[:-1])


def language_of(path: str):
    if is_noise(path):
        return None
    return LANG_BY_EXT.get(PurePosixPath(path).suffix.lower())


def heat_level(count: int, max_count: int) -> int:
    """Map a day's commit count to 0..4 (0 = no commits)."""
    if count <= 0:
        return 0
    if count == 1 or max_count <= 1:
        return 1 if max_count > 1 else 4
    return min(4, 1 + math.ceil((count - 1) / (max_count - 1) * 3))


def longest_streak(days):
    """(length, start, end) of the longest run of consecutive days."""
    best = (0, None, None)
    run, start, prev = 0, None, None
    for d in sorted(days):
        if prev is not None and (d - prev).days == 1:
            run += 1
        else:
            run, start = 1, d
        if run > best[0]:
            best = (run, start, d)
        prev = d
    return best


@dataclass
class Persona:
    emoji: str
    title: str
    blurb: str


def pick_persona(commits: int, active_days: int, streak: int, night: float, early: float, weekend: float) -> Persona:
    if commits < 10:
        return Persona("🌱", "Fresh Starter", "Just getting going. The best commit is the next one.")
    if night >= 0.35:
        return Persona("🦉", "Night Owl", "The best code ships after dark.")
    if early >= 0.30:
        return Persona("🐦", "Early Bird", "Coffee, sunrise, git push.")
    if weekend >= 0.40:
        return Persona("⚔️", "Weekend Warrior", "Weekdays are for work. Weekends are for real projects.")
    if streak >= 14:
        return Persona("🔥", "Streak Machine", "Day after day, the green squares keep coming.")
    if active_days >= 150:
        return Persona("⚙️", "Daily Grinder", "Show up, commit, repeat.")
    return Persona("🧱", "Steady Builder", "One commit at a time, something real gets built.")


@dataclass
class Stats:
    year: int
    commits: int
    active_days: int
    longest_streak: int
    streak_start: object
    streak_end: object
    lines_added: int
    lines_deleted: int
    hours: list
    weekdays: list
    daily: dict
    languages: list  # [(name, lines)] biggest first
    repos: list  # [(name, commits)] biggest first
    busiest_day: object  # (date, count) or None
    top_word: object  # (word, commits) or None
    fix_commits: int
    night_share: float
    weekend_share: float
    persona: Persona

    def to_dict(self) -> dict:
        iso = lambda d: d.isoformat() if d else None  # noqa: E731
        return {
            "year": self.year,
            "commits": self.commits,
            "active_days": self.active_days,
            "longest_streak": {"days": self.longest_streak, "start": iso(self.streak_start), "end": iso(self.streak_end)},
            "lines_added": self.lines_added,
            "lines_deleted": self.lines_deleted,
            "hours": self.hours,
            "weekdays": self.weekdays,
            "languages": [{"name": n, "lines": v} for n, v in self.languages],
            "repos": [{"name": n, "commits": v} for n, v in self.repos],
            "busiest_day": {"date": iso(self.busiest_day[0]), "commits": self.busiest_day[1]} if self.busiest_day else None,
            "top_word": {"word": self.top_word[0], "commits": self.top_word[1]} if self.top_word else None,
            "fix_commits": self.fix_commits,
            "night_share": round(self.night_share, 3),
            "weekend_share": round(self.weekend_share, 3),
            "persona": {"emoji": self.persona.emoji, "title": self.persona.title, "blurb": self.persona.blurb},
            "daily": {iso(d): n for d, n in sorted(self.daily.items())},
        }


def compute(commits: list, year: int) -> Stats:
    hours = [0] * 24
    weekdays = [0] * 7
    daily: Counter = Counter()
    repos: Counter = Counter()
    langs: Counter = Counter()
    words: Counter = Counter()
    added = deleted = fix = 0

    for c in commits:
        daily[c.when.date()] += 1
        hours[c.when.hour] += 1
        weekdays[c.when.weekday()] += 1
        repos[c.repo] += 1
        subject = c.subject.lower()
        if FIX_RE.search(subject):
            fix += 1
        for w in set(WORD_RE.findall(subject)):
            if w not in STOP_WORDS:
                words[w] += 1
        for path, a, d in c.files:
            if is_noise(path):
                continue
            added += a
            deleted += d
            lang = language_of(path)
            if lang:
                langs[lang] += a + d

    n = len(commits)
    streak, s_start, s_end = longest_streak(daily.keys())
    night = (sum(hours[22:]) + sum(hours[:5])) / n if n else 0.0
    early = sum(hours[5:9]) / n if n else 0.0
    weekend = (weekdays[5] + weekdays[6]) / n if n else 0.0
    busiest = max(daily.items(), key=lambda kv: (kv[1], -kv[0].toordinal())) if daily else None
    top_word = words.most_common(1)[0] if words else None

    return Stats(
        year=year,
        commits=n,
        active_days=len(daily),
        longest_streak=streak,
        streak_start=s_start,
        streak_end=s_end,
        lines_added=added,
        lines_deleted=deleted,
        hours=hours,
        weekdays=weekdays,
        daily=dict(daily),
        languages=langs.most_common(),
        repos=repos.most_common(),
        busiest_day=busiest,
        top_word=top_word,
        fix_commits=fix,
        night_share=night,
        weekend_share=weekend,
        persona=pick_persona(n, len(daily), streak, night, early, weekend),
    )
