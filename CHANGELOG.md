# Changelog

## 0.2.0

- **PNG export**: `--png` writes a PNG next to the SVG, and `-o card.png` writes only a PNG.
  Uses whichever renderer is installed (Chrome/Chromium, rsvg-convert, cairosvg, Inkscape or ImageMagick), so git-wrapped itself still has zero dependencies.
- If PNG export isn't possible the SVG card is still saved and the exit code is 3.
- Fix: the "favorite commit word" no longer duplicates the "fix" counter.

## 0.1.0

- First release: terminal report, SVG card, personas, multi-repo scan, JSON output.
