"""Read commits out of local git repositories (stdlib + the `git` binary only)."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

SKIP_DIRS = {"node_modules", "venv", "env", "__pycache__", "site-packages", "dist", "build", "target"}


@dataclass
class Commit:
    repo: str
    sha: str
    when: datetime  # naive, in the author's own local time
    subject: str
    files: list = field(default_factory=list)  # [(path, added, deleted)]


def find_repos(root, max_depth: int = 3) -> list:
    """Return `root` itself if it is a repo, otherwise every repo found below it."""
    root = Path(root).expanduser().resolve()
    if (root / ".git").exists():
        return [root]

    found: list = []

    def walk(directory: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(p for p in directory.iterdir() if p.is_dir() and not p.is_symlink())
        except OSError:
            return
        for p in entries:
            if p.name.startswith(".") or p.name in SKIP_DIRS:
                continue
            if (p / ".git").exists():
                found.append(p)
            else:
                walk(p, depth + 1)

    walk(root, 1)
    return found


def default_authors() -> list:
    """The name and email from the user's git config (used to filter commits)."""
    out = []
    for key in ("user.email", "user.name"):
        try:
            r = subprocess.run(["git", "config", "--get", key], capture_output=True, text=True)
        except FileNotFoundError:
            raise RuntimeError("git was not found on PATH") from None
        value = r.stdout.strip()
        if value:
            out.append(value)
    return out


def clean_path(path: str) -> str:
    """Resolve numstat rename syntax: `src/{old => new}/x.py` and `a.py => b.py`."""
    if " => " not in path:
        return path
    if "{" in path and "}" in path:
        prefix, rest = path.split("{", 1)
        middle, suffix = rest.split("}", 1)
        new = middle.split(" => ")[-1]
        return (prefix + new + suffix).replace("//", "/")
    return path.split(" => ")[-1]


def read_commits(repo, year: int, authors=None) -> list:
    cmd = [
        "git", "-c", "core.quotepath=false", "-C", str(repo), "log",
        "--all", "--no-merges",
        f"--since={year - 1}-12-30", f"--until={year + 1}-01-02",
        "--pretty=format:@@\t%H\t%aI\t%s", "--numstat",
    ]
    if authors:
        cmd += ["-i", "-F"] + [f"--author={a}" for a in authors]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise RuntimeError("git was not found on PATH") from None
    if r.returncode != 0:  # e.g. a repo with no commits yet
        return []

    commits: list = []
    cur = None
    name = Path(repo).name
    for line in r.stdout.splitlines():
        if line.startswith("@@\t"):
            _, sha, iso, subject = line.split("\t", 3)
            when = datetime.fromisoformat(iso).replace(tzinfo=None)
            if when.year != year:
                cur = None
                continue
            cur = Commit(repo=name, sha=sha, when=when, subject=subject)
            commits.append(cur)
        elif cur is not None and line.strip():
            parts = line.split("\t", 2)
            if len(parts) == 3:
                a, d, path = parts
                cur.files.append((clean_path(path), int(a) if a.isdigit() else 0, int(d) if d.isdigit() else 0))
    return commits


def collect(path, year: int, authors=None, max_depth: int = 3):
    """Return (repos, commits) for the year, de-duplicated across repos, oldest first."""
    repos = find_repos(path, max_depth)
    seen: set = set()
    commits: list = []
    for repo in repos:
        for c in read_commits(repo, year, authors):
            if c.sha in seen:
                continue
            seen.add(c.sha)
            commits.append(c)
    commits.sort(key=lambda c: c.when)
    return repos, commits
