"""Render a shareable 1080x1350 SVG card (no dependencies)."""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from xml.sax.saxutils import escape

from .stats import Stats, heat_level

W, H, PAD = 1080, 1350, 60
FONT = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
TILE, TEXT, MUTED, ACCENT = "#161b22", "#e6edf3", "#8b949e", "#39d353"
HEAT = ["#21262d", "#0e4429", "#006d32", "#26a641", "#39d353"]
LANG_COLORS = ["#58a6ff", "#f78166", "#d2a8ff", "#ffa657"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fmt_compact(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1000:.0f}k"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def fmt_hour(h: int) -> str:
    return f"{h % 12 or 12}{'am' if h < 12 else 'pm'}"


def fmt_day(d: date) -> str:
    return f"{MONTHS[d.month - 1]} {d.day}"


def _text(x, y, s, size, fill=TEXT, weight=400, anchor="start", extra="") -> str:
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}" text-anchor="{anchor}"{extra}>{escape(str(s))}</text>'
    )


def render_svg(stats: Stats, name=None) -> str:
    o: list = []
    add = o.append
    add(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="{FONT}">'
    )
    add(f"<title>Git Wrapped {stats.year}</title>")
    add('<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#0d1117"/><stop offset="1" stop-color="#0b1d16"/>'
        "</linearGradient></defs>")
    add(f'<rect width="{W}" height="{H}" fill="url(#bg)"/>')

    # ── header ────────────────────────────────────────────────────────────
    add(_text(PAD, 95, "GIT WRAPPED", 22, ACCENT, 700, extra=' letter-spacing="6"'))
    if name:
        add(_text(W - PAD, 95, name, 22, MUTED, 500, "end"))
    add(_text(PAD, 190, stats.year, 96, TEXT, 800))
    p = stats.persona
    add(_text(PAD, 252, f"{p.emoji} {p.title}", 40, TEXT, 700))
    add(_text(PAD, 290, p.blurb, 22, MUTED))

    # ── headline tiles ────────────────────────────────────────────────────
    tiles = [
        (f"{stats.commits:,}", "commits"),
        (f"{stats.active_days}", "active days"),
        (f"{stats.longest_streak}d", "longest streak"),
        (fmt_compact(stats.lines_added + stats.lines_deleted), "lines changed"),
    ]
    gap = 20
    tw = (W - 2 * PAD - gap * (len(tiles) - 1)) // len(tiles)
    for i, (val, label) in enumerate(tiles):
        x = PAD + i * (tw + gap)
        add(f'<rect x="{x}" y="330" width="{tw}" height="130" rx="16" fill="{TILE}"/>')
        add(_text(x + 22, 392, val, 44, ACCENT, 800))
        add(_text(x + 22, 430, label, 18, MUTED))

    # ── contribution heatmap ──────────────────────────────────────────────
    add(_text(PAD, 520, "Your year, commit by commit", 24, TEXT, 600))
    jan1 = date(stats.year, 1, 1)
    offset = (jan1.weekday() + 1) % 7  # Sunday-first, like GitHub
    n_days = 366 if calendar.isleap(stats.year) else 365
    cols = (n_days - 1 + offset) // 7 + 1
    step = min(18, (W - 2 * PAD) // cols)
    cell = step - 3
    gy = 580
    mx = max(stats.daily.values(), default=0)
    for m in range(1, 13):
        col = ((date(stats.year, m, 1) - jan1).days + offset) // 7
        add(_text(PAD + col * step, gy - 12, MONTHS[m - 1], 13, MUTED))
    for i in range(n_days):
        d = jan1 + timedelta(days=i)
        col, row = divmod(i + offset, 7)
        c = stats.daily.get(d, 0)
        tip = f"{fmt_day(d)}: {c} commit{'s' if c != 1 else ''}"
        add(
            f'<rect x="{PAD + col * step}" y="{gy + row * step}" width="{cell}" height="{cell}" '
            f'rx="3" fill="{HEAT[heat_level(c, mx)]}"><title>{tip}</title></rect>'
        )
    ly = gy + 7 * step + 26
    sq0 = W - PAD - 48 - 5 * 18
    add(_text(W - PAD, ly + 11, "More", 14, MUTED, anchor="end"))
    for i, col_hex in enumerate(HEAT):
        add(f'<rect x="{sq0 + i * 18}" y="{ly}" width="14" height="14" rx="3" fill="{col_hex}"/>')
    add(_text(sq0 - 8, ly + 11, "Less", 14, MUTED, anchor="end"))

    # ── hour-of-day chart ─────────────────────────────────────────────────
    add(_text(PAD, 800, "When you code", 24, TEXT, 600))
    mxh = max(stats.hours) or 1
    peak = stats.hours.index(max(stats.hours))
    if max(stats.hours) > 0:
        add(_text(W - PAD, 800, f"peak: {fmt_hour(peak)}", 20, MUTED, anchor="end"))
    base, max_bar = 945, 120
    for h, v in enumerate(stats.hours):
        bh = max(3, round(v / mxh * max_bar))
        x = PAD + h * 40 + 4
        fill, opacity = (ACCENT, 1) if (h == peak and v > 0) else ("#2ea043", 0.5)
        add(
            f'<rect x="{x}" y="{base - bh}" width="32" height="{bh}" rx="6" '
            f'fill="{fill}" fill-opacity="{opacity}"><title>{fmt_hour(h)}: {v} commits</title></rect>'
        )
        if h in (0, 6, 12, 18):
            add(_text(x + 16, base + 28, fmt_hour(h), 14, MUTED, anchor="middle"))

    # ── languages ─────────────────────────────────────────────────────────
    add(_text(PAD, 1015, "Top languages", 24, TEXT, 600))
    langs = stats.languages[:4]
    total = sum(v for _, v in stats.languages) or 1
    if langs:
        for i, (lang, v) in enumerate(langs):
            y = 1045 + i * 38
            add(_text(PAD, y + 17, lang, 20, TEXT, 500))
            bw = max(8, round(v / langs[0][1] * 600))
            add(f'<rect x="{PAD + 170}" y="{y}" width="{bw}" height="22" rx="11" fill="{LANG_COLORS[i % 4]}"/>')
            add(_text(W - PAD, y + 17, f"{round(v / total * 100)}%", 18, MUTED, anchor="end"))
    else:
        add(_text(PAD, 1075, "No recognised source files this year.", 20, MUTED))

    # ── fun facts ─────────────────────────────────────────────────────────
    facts = []
    if stats.busiest_day:
        d, n = stats.busiest_day
        facts.append(("Busiest day", f"{fmt_day(d)} · {n} commits"))
    if stats.top_word:
        facts.append(("Favorite commit word", f"“{stats.top_word[0]}” · {stats.top_word[1]}×"))
    facts.append(("After dark", f"{round(stats.night_share * 100)}% after 10pm"))
    fgap = 30
    fw = (W - 2 * PAD - fgap * (len(facts) - 1)) // len(facts)
    for i, (label, value) in enumerate(facts):
        x = PAD + i * (fw + fgap)
        add(f'<rect x="{x}" y="1210" width="{fw}" height="90" rx="16" fill="{TILE}"/>')
        add(_text(x + 20, 1240, label, 16, MUTED))
        add(_text(x + 20, 1278, value, 22, TEXT, 700))

    add(_text(W // 2, 1335, "made with git-wrapped", 15, MUTED, anchor="middle"))
    add("</svg>")
    return "\n".join(o)
