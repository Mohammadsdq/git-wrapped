"""Command line interface."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

from . import __version__
from .collect import collect, default_authors
from .png import PngError, svg_to_png
from .render import render_svg
from .stats import compute
from .terminal import render_terminal


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="git-wrapped",
        description="Your year in git: a terminal report plus a shareable SVG card. Runs 100%% locally.",
    )
    p.add_argument("path", nargs="?", default=".", help="a git repo, or a folder containing repos (default: .)")
    p.add_argument("-y", "--year", type=int, default=date.today().year, help="year to summarise (default: this year)")
    p.add_argument("-a", "--author", action="append", help="author name or email to count (repeatable). Default: your git config")
    p.add_argument("--all-authors", action="store_true", help="count commits from everyone")
    p.add_argument("-o", "--output", help="where to write the card: *.svg, or *.png for a PNG only (default: git-wrapped-<year>.svg)")
    p.add_argument("--png", action="store_true", help="also export a PNG next to the SVG (needs Chrome, rsvg-convert, Inkscape, ImageMagick or cairosvg)")
    p.add_argument("--name", help="name or @handle to print on the card")
    p.add_argument("--no-svg", action="store_true", help="only print the terminal report (write no files)")
    p.add_argument("--json", action="store_true", help="print the raw stats as JSON instead of the report")
    p.add_argument("--no-color", action="store_true", help="disable ANSI colours")
    p.add_argument("--depth", type=int, default=3, help="how deep to look for repos inside a folder (default: 3)")
    p.add_argument("--version", action="version", version=f"git-wrapped {__version__}")
    return p


def write_card(stats, args) -> int:
    """Write the SVG card and/or a PNG. Returns a process exit code."""
    log = sys.stderr if args.json else sys.stdout
    out = Path(args.output or f"git-wrapped-{args.year}.svg")
    svg_text = render_svg(stats, name=args.name)

    png_only = out.suffix.lower() == ".png"
    if not png_only and not args.png:
        out.write_text(svg_text, encoding="utf-8")
        print(f"  Card saved to {out}", file=log)
        return 0

    png_path = out if png_only else out.with_suffix(".png")
    svg_path = out.with_suffix(".svg") if png_only else out
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "card.svg" if png_only else svg_path
        src.write_text(svg_text, encoding="utf-8")
        try:
            svg_to_png(src, png_path)
        except PngError as e:
            if png_only:  # don't lose the card: keep the SVG instead
                svg_path.write_text(svg_text, encoding="utf-8")
            print(f"  PNG export failed: {e}", file=sys.stderr)
            print(f"  SVG card saved to {svg_path}", file=sys.stderr)
            return 3
    saved = str(png_path) if png_only else f"{png_path} and {svg_path}"
    print(f"  Card saved to {saved}", file=log)
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.all_authors:
            authors = None
        elif args.author:
            authors = args.author
        else:
            authors = default_authors() or None
            if authors is None:
                print("No git user configured; counting commits from all authors.", file=sys.stderr)
        repos, commits = collect(args.path, args.year, authors, args.depth)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if not repos:
        print(f"No git repositories found in {args.path}", file=sys.stderr)
        return 1
    if not commits:
        who = ", ".join(authors) if authors else "anyone"
        print(
            f"No commits by {who} in {args.year} across {len(repos)} repo(s).\n"
            "Try --all-authors, --author EMAIL, or --year.",
            file=sys.stderr,
        )
        return 1

    stats = compute(commits, args.year)

    if args.json:
        print(json.dumps(stats.to_dict(), ensure_ascii=False, indent=2))
    else:
        use_color = sys.stdout.isatty() and not args.no_color and "NO_COLOR" not in os.environ
        width = shutil.get_terminal_size((100, 24)).columns
        print(render_terminal(stats, color=use_color, width=width))

    if not args.no_svg and (not args.json or args.output or args.png):
        return write_card(stats, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
