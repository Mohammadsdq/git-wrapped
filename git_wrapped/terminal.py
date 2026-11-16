"""Colourful terminal report."""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from .stats import Stats, heat_level

BLOCKS = "▁▂▃▄▅▆▇█"
LEVEL_256 = [236, 22, 28, 34, 46]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def render_terminal(stats: Stats, color: bool = True, width: int = 100) -> str:
    def paint(text: str, code: str) -> str:
        return f"\x1b[{code}m{text}\x1b[0m" if color else text

    bold = lambda t: paint(t, "1")  # noqa: E731
    dim = lambda t: paint(t, "2")  # noqa: E731
    green = lambda t: paint(t, "38;5;46")  # noqa: E731

    out: list = []
    p = stats.persona
    out.append("")
    out.append(f"  {bold('Git Wrapped')} {green(str(stats.year))}   {p.emoji} {bold(p.title)}")
    out.append(f"  {dim(p.blurb)}")
    out.append("")
    out.append(
        f"  {green(f'{stats.commits:,}')} commits · {green(str(stats.active_days))} active days · "
        f"{green(str(stats.longest_streak))}-day streak · "
        f"{green('+' + format(stats.lines_added, ','))} / {paint('-' + format(stats.lines_deleted, ','), '38;5;203')} lines"
    )
    out.append("")

    # heatmap
    jan1 = date(stats.year, 1, 1)
    offset = (jan1.weekday() + 1) % 7
    n_days = 366 if calendar.isleap(stats.year) else 365
    cols = (n_days - 1 + offset) // 7 + 1
    unit = 2 if width >= cols * 2 + 8 else 1
    mx = max(stats.daily.values(), default=0)

    header = [" "] * (4 + cols * unit)
    last_end = 0
    for m in range(1, 13):
        col = ((date(stats.year, m, 1) - jan1).days + offset) // 7
        pos = 4 + col * unit
        if pos >= last_end and pos + 3 <= len(header):
            header[pos:pos + 3] = list(MONTHS[m - 1])
            last_end = pos + 4
    out.append("  " + dim("".join(header)))

    grid = [[0] * cols for _ in range(7)]
    for i in range(n_days):
        col, row = divmod(i + offset, 7)
        grid[row][col] = heat_level(stats.daily.get(jan1 + timedelta(days=i), 0), mx)
    labels = {1: "Mon", 3: "Wed", 5: "Fri"}
    for row in range(7):
        cells = ""
        for col in range(cols):
            ch = paint("■", f"38;5;{LEVEL_256[grid[row][col]]}") if color else "·░▒▓█"[grid[row][col]]
            cells += ch + (" " if unit == 2 else "")
        out.append("  " + dim(labels.get(row, "   ")) + " " + cells)
    out.append("")

    # hours
    mxh = max(stats.hours) or 1
    spark = ""
    for h, v in enumerate(stats.hours):
        spark += BLOCKS[min(7, round(v / mxh * 7))] if v else "·"
    out.append(f"  {bold('When you code')}")
    out.append("  " + green(spark))
    out.append("  " + dim("0     6     12    18    "))
    out.append("")

    # languages
    if stats.languages:
        out.append(f"  {bold('Top languages')}")
        top = stats.languages[0][1]
        total = sum(v for _, v in stats.languages)
        for lang, v in stats.languages[:5]:
            n = max(1, round(v / top * 24))
            out.append(f"  {lang:<12} {green('█' * n)}{dim('░' * (24 - n))} {round(v / total * 100):>3}%")
        out.append("")

    # fun facts
    if stats.busiest_day:
        d, n = stats.busiest_day
        out.append(f"  📅 Busiest day: {bold(f'{MONTHS[d.month - 1]} {d.day}')} ({n} commits)")
    if stats.top_word:
        out.append(f"  💬 Favorite commit word: {bold(stats.top_word[0])} ({stats.top_word[1]}×)")
    out.append(f"  🐛 Commits that mention a fix: {bold(str(stats.fix_commits))}")
    out.append(f"  🌙 Commits after 10pm: {bold(str(round(stats.night_share * 100)) + '%')}")
    if len(stats.repos) > 1:
        top_repos = ", ".join(f"{n} ({c})" for n, c in stats.repos[:3])
        out.append(f"  📦 Busiest repos: {top_repos}")
    out.append("")
    return "\n".join(out)
