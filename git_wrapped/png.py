"""Optional PNG export.

git-wrapped has no hard dependencies, so PNG export borrows whichever SVG
renderer is already on the machine: Chrome/Chromium, rsvg-convert, cairosvg,
Inkscape or ImageMagick. Backends are tried in that order until one works.
"""
from __future__ import annotations

import os
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

W, H = 1080, 1350
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

NO_BACKEND_MSG = (
    "PNG export needs an SVG renderer. Install one of: Google Chrome/Chromium, "
    "librsvg (rsvg-convert), Inkscape, ImageMagick, or `pip install cairosvg`. "
    "(The SVG card works without any of them.)"
)

CHROME_NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge")
CHROME_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)


class PngError(RuntimeError):
    """PNG export is unavailable or failed."""


def _run(cmd: list, timeout: int = 90) -> None:
    name = Path(cmd[0]).name
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise PngError(f"{name} timed out") from None
    if r.returncode != 0:
        raise PngError(f"{name} exited with {r.returncode}: {(r.stderr or r.stdout).strip()[:200]}")


def _find_chrome():
    for name in CHROME_NAMES:
        found = shutil.which(name)
        if found:
            return found
    for path in CHROME_PATHS:
        if os.path.exists(path):
            return path
    return None


def _chrome(exe: str, svg: Path, png: Path) -> None:
    with tempfile.TemporaryDirectory() as profile:  # fresh profile: works even if Chrome is already open
        cmd = [
            exe, "--headless", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
            f"--window-size={W},{H}", f"--user-data-dir={profile}", f"--screenshot={png.resolve()}",
        ]
        if hasattr(os, "geteuid") and os.geteuid() == 0:  # Chrome refuses to start as root otherwise
            cmd.append("--no-sandbox")
        cmd.append(svg.resolve().as_uri())
        _run(cmd)


def _rsvg(exe: str, svg: Path, png: Path) -> None:
    _run([exe, "-w", str(W), "-h", str(H), "-o", str(png), str(svg)])


def _inkscape(exe: str, svg: Path, png: Path) -> None:
    _run([exe, str(svg), "--export-type=png", f"--export-filename={png}", "-w", str(W)])


def _magick(exe: str, svg: Path, png: Path) -> None:
    _run([exe, "-background", "none", "-density", "96", str(svg), "-resize", f"{W}x{H}", str(png)])


def _cairosvg(svg: Path, png: Path) -> None:
    try:
        import cairosvg  # type: ignore
        cairosvg.svg2png(url=str(svg), write_to=str(png), output_width=W, output_height=H)
    except Exception as e:  # ImportError, or a missing libcairo
        raise PngError(f"cairosvg: {e}") from None


def available_backends() -> list:
    """[(name, fn(svg, png))] for every renderer found on this machine, best first."""
    found: list = []
    chrome = _find_chrome()
    if chrome:
        found.append(("chrome", lambda s, p, e=chrome: _chrome(e, s, p)))
    rsvg = shutil.which("rsvg-convert")
    if rsvg:
        found.append(("rsvg-convert", lambda s, p, e=rsvg: _rsvg(e, s, p)))
    try:
        import cairosvg  # type: ignore  # noqa: F401
        found.append(("cairosvg", _cairosvg))
    except Exception:
        pass
    inkscape = shutil.which("inkscape")
    if inkscape:
        found.append(("inkscape", lambda s, p, e=inkscape: _inkscape(e, s, p)))
    magick = shutil.which("magick") or (shutil.which("convert") if os.name != "nt" else None)
    if magick:
        found.append(("imagemagick", lambda s, p, e=magick: _magick(e, s, p)))
    return found


def _verify(png: Path) -> None:
    if not png.exists():
        raise PngError("no file was written")
    data = png.read_bytes()
    if len(data) < 1000 or not data.startswith(PNG_MAGIC):
        raise PngError("output is not a valid PNG")
    width, height = struct.unpack(">II", data[16:24])
    if (width, height) != (W, H):
        raise PngError(f"unexpected size {width}x{height} (wanted {W}x{H})")


def svg_to_png(svg, png, backends=None) -> str:
    """Render `svg` to `png` with the first backend that works. Returns the backend's name."""
    svg, png = Path(svg), Path(png)
    backends = available_backends() if backends is None else backends
    if not backends:
        raise PngError(NO_BACKEND_MSG)

    png.parent.mkdir(parents=True, exist_ok=True)
    tmp = png.parent / f".{png.stem}.tmp.png"  # render beside the target, then swap in
    errors: list = []
    for name, render in backends:
        try:
            tmp.unlink(missing_ok=True)
            render(svg, tmp)
            _verify(tmp)
            os.replace(tmp, png)
            return name
        except Exception as e:  # try the next backend
            errors.append(f"{name}: {e}")
        finally:
            tmp.unlink(missing_ok=True)
    raise PngError("no renderer produced a PNG:\n    " + "\n    ".join(errors))
