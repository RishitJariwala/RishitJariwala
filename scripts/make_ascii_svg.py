"""
ASCII portrait SVG generator with self-printing animation.

Converts a processed grayscale image into an animated SVG where each row
types itself in from left to right with a blinking cursor, then freezes.

Animation approach (GitHub-safe):
  - Uses CSS @keyframes only (no SMIL <animate>)
  - Each row: text rendered, then a background-colored overlay rect animates
    from full-width → 0 using transform: scaleX() with transform-origin: right
  - A cursor rect follows the overlay edge using transform: translateX()
  - All animations use fill-mode: forwards and play once

Usage:
    python scripts/make_ascii_svg.py [--config <path>]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

# Ensure project root is on sys.path so scripts package is importable
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import cv2
import numpy as np

from scripts.utils import load_config, setup_logging, validate_svg

logger = logging.getLogger("make_ascii_svg")

RAMP_DEFAULT = " .`:-=+*cs#%@"  # bright (sparse) → dark (dense)
CHAR_ASPECT = 0.5  # width/height ratio of a monospace character


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate animated ASCII portrait SVG from processed photo."
    )
    parser.add_argument(
        "--config", "-c", type=str, default="config.yaml",
    )
    parser.add_argument(
        "--input", "-i", type=str, default=None,
    )
    parser.add_argument("--output", "-o", type=str, default=None)
    parser.add_argument("--force", "-f", action="store_true", default=False)
    parser.add_argument("--verbose", "-v", action="store_true", default=False)
    return parser.parse_args(argv)


def load_grayscale(path: str) -> np.ndarray:
    """Load a grayscale image as a 2D numpy array (0–255)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Prepped image not found: {p.resolve()}")
    img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Failed to load image: {path}")
    logger.info(f"Loaded image: {img.shape[1]}x{img.shape[0]}")
    return img


def downsample_to_grid(img: np.ndarray, grid_width: int) -> np.ndarray:
    """Resize image to target character grid width, preserving aspect ratio.

    Uses CHAR_ASPECT because characters are taller than wide.
    """
    h, w = img.shape
    aspect = h / w
    grid_height = max(1, int(grid_width * aspect * CHAR_ASPECT))
    resized = cv2.resize(img, (grid_width, grid_height), interpolation=cv2.INTER_AREA)
    logger.info(f"Grid size: {resized.shape[1]}x{resized.shape[0]} chars")
    return resized


def trim_blank_rows(grid: np.ndarray, ramp: str) -> np.ndarray:
    """Remove entirely blank (all-spaces) rows from top and bottom."""
    rows, cols = grid.shape
    non_blank = np.ones(rows, dtype=bool)
    for r in range(rows):
        row_chars = []
        for c in range(cols):
            pixel = int(grid[r, c])
            inverted = 255 - pixel
            idx = int(inverted / 255.0 * (len(ramp) - 1))
            row_chars.append(ramp[idx])
        if all(ch == ' ' for ch in row_chars):
            non_blank[r] = False
    if not np.any(non_blank):
        return grid
    trimmed = grid[non_blank]
    logger.info(f"Trimmed from {rows} to {len(trimmed)} rows (removed {rows - len(trimmed)} blank rows)")
    return trimmed


def enhance_contrast(img: np.ndarray) -> np.ndarray:
    """Apply CLAHE for local contrast enhancement."""
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    return clahe.apply(img)


def pixel_to_glyph(pixel_value: int, ramp: str) -> str:
    """Map grayscale pixel (0=black, 255=white) to a glyph from the ramp.

    Ramp is ordered bright→dark (sparse→dense). Leading space = background.
    """
    if not ramp:
        return " "
    inverted = 255 - pixel_value
    index = int(inverted / 255.0 * (len(ramp) - 1))
    index = max(0, min(index, len(ramp) - 1))
    return ramp[index]


def generate_svg(
    grid: np.ndarray,
    ramp: str,
    font_family: str,
    font_size: int,
    line_height: float,
    char_color: str,
    bg_color: str,
    typing_speed_ms: int,
    cursor_blink_ms: int,
) -> str:
    """
    Generate animated SVG using CSS @keyframes only (no SMIL).

    Technique per row:
      1. Render full row text in a <text> element
      2. Place a <rect> overlay (bg_color) on top, with transform-origin: right
      3. Animate overlay transform: scaleX(1) → scaleX(0) to reveal text LTR
      4. A cursor <rect> follows the right edge of the overlay
    """
    rows, cols = grid.shape
    char_w = round(font_size * 0.6, 1)
    char_h = round(font_size * line_height, 1)
    padding = 8

    # Build glyph map — trim trailing spaces per row for natural animation
    glyph_rows: list[str] = []
    for r in range(rows):
        row_chars: list[str] = []
        for c in range(cols):
            pixel = int(grid[r, c])
            glyph = pixel_to_glyph(pixel, ramp)
            row_chars.append(glyph)
        text = "".join(row_chars).rstrip()
        glyph_rows.append(text)

    # Compute dimensions (use full width for alignment even with trimmed rows)
    row_width_px = round(cols * char_w)
    svg_w = row_width_px + 2 * padding
    svg_h = padding * 2 + rows * char_h + char_h * 2

    # Per-row animation data
    row_data: list[dict] = []
    for r in range(rows):
        text = glyph_rows[r]
        trimmed_len = len(text)
        reveal_width = round(trimmed_len * char_w)
        dur = max(1, trimmed_len * typing_speed_ms) if trimmed_len > 0 else 1
        delay = r * 50
        row_data.append({
            "text": text,
            "width": reveal_width,
            "duration": dur,
            "delay": delay,
            "y": padding + r * char_h,
            "end_delay": delay + dur,
        })

    total_anim_duration = max(d["end_delay"] for d in row_data) + 500

    lines: list[str] = []
    lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w:.0f}" height="{svg_h:.0f}"')
    lines.append(f'     viewBox="0 0 {svg_w:.0f} {svg_h:.0f}"')
    lines.append(f'     style="background-color:{bg_color};">')

    # ── CSS Keyframes ─────────────────────────────────────────────────
    lines.append("  <style>")
    lines.append("    @keyframes reveal {")
    lines.append("      from { transform: scaleX(1); }")
    lines.append("      to   { transform: scaleX(0); }")
    lines.append("    }")
    lines.append("    @keyframes blink {")
    lines.append("      0%, 49% { opacity: 1; }")
    lines.append("      50%, 100% { opacity: 0; }")
    lines.append("    }")
    lines.append("    @keyframes fadeIn {")
    lines.append("      from { opacity: 0; }")
    lines.append("      to   { opacity: 1; }")
    lines.append("    }")
    # Per-row cursor slide keyframes
    for r, rd in enumerate(row_data):
        if rd["width"] == 0:
            continue
        lines.append(f'    @keyframes cursor{r} {{')
        lines.append(f'      from {{ transform: translateX(0); }}')
        lines.append(f'      to   {{ transform: translateX({rd["width"]}px); }}')
        lines.append(f'    }}')
    lines.append("    @media (prefers-reduced-motion: reduce) {")
    lines.append("      * { animation-duration: 0s !important; animation-delay: 0s !important; }")
    lines.append("    }")
    lines.append("  </style>")

    # ── Defs ──────────────────────────────────────────────────────────
    lines.append("  <defs>")
    cursor_w = max(2, round(font_size * 0.4))
    cursor_h = round(char_h - 2)
    lines.append(f'    <rect id="cursor" width="{cursor_w}" height="{cursor_h}" fill="{char_color}" rx="1" />')
    lines.append("  </defs>")

    # ── Render rows ───────────────────────────────────────────────────
    for r, rd in enumerate(row_data):
        text = rd["text"]
        y_text = rd["y"]
        dur = rd["duration"]
        delay = rd["delay"]
        end_delay = rd["end_delay"]
        reveal_w = rd["width"]

        if reveal_w == 0:
            continue

        # Escape XML
        escaped = (text.replace("&", "&amp;")
                      .replace("<", "&lt;")
                      .replace(">", "&gt;")
                      .replace('"', "&quot;"))

        # ── Background text (always visible) ──────────────────────────
        text_y = round(y_text + font_size * 0.85)
        lines.append(f'  <text x="{padding}" y="{text_y}"'
                     f' font-family="{font_family}" font-size="{font_size}"'
                     f' fill="{char_color}" xml:space="preserve">'
                     f'{escaped}</text>')

        # ── Overlay rect (shrinks to reveal) ──────────────────────────
        overlay_y = round(y_text)
        overlay_h = round(char_h)
        lines.append(f'  <rect x="{padding}" y="{overlay_y}"'
                     f' width="{reveal_w}" height="{overlay_h}"'
                     f' fill="{bg_color}"'
                     f' style="transform-origin: right center;'
                     f' animation: reveal {dur}ms ease-out {delay}ms forwards;" />')

        # ── Cursor (follows right edge of overlay) ────────────────────
        cursor_y = round(y_text + 1)
        lines.append(f'  <g style="animation: cursor{r} {dur}ms ease-out {delay}ms forwards;">')
        lines.append(f'    <use href="#cursor" x="{padding}" y="{cursor_y}"')
        blink_iter = 'infinite' if r == len(row_data) - 1 else '2'
        lines.append(f'         style="animation: blink {cursor_blink_ms}ms step-end {blink_iter};'
                     f'                       animation-delay: {end_delay}ms;" />')
        lines.append(f'  </g>')

    # ── Terminal prompt cursor at bottom ──────────────────────────────
    prompt_y = round(padding + rows * char_h + font_size + 6)
    lines.append(f'  <text x="{padding}" y="{prompt_y}"'
                 f' font-family="{font_family}" font-size="{font_size}"'
                 f' fill="{char_color}"'
                 f' style="animation: fadeIn 400ms ease-out {total_anim_duration}ms forwards;">')
    lines.append(f'    █')
    lines.append(f'  </text>')

    # ── Footer credit ─────────────────────────────────────────────────
    credit_y = prompt_y + font_size + 4
    lines.append(f'  <text x="{padding}" y="{credit_y}"'
                 f' font-family="{font_family}" font-size="{max(6, font_size - 2)}"'
                 f' fill="{char_color}" opacity="0.5"'
                 f' style="animation: fadeIn 500ms ease-out {total_anim_duration + 200}ms forwards;">')
    lines.append(f'    RishitJariwala@github ~ $ █')
    lines.append(f'  </text>')

    lines.append("</svg>")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    setup_logging(level=logging.DEBUG if args.verbose else logging.INFO)

    config = load_config(args.config)
    ascii_cfg = config.get("ascii", {})

    input_path = args.input or "assets/source-prepped.png"
    output_path = args.output or ascii_cfg.get("output_path", "ascii-portrait.svg")

    try:
        img = load_grayscale(input_path)
    except (FileNotFoundError, ValueError) as exc:
        logger.error(str(exc))
        return 1

    # Enhance contrast
    img = enhance_contrast(img)

    grid_width = ascii_cfg.get("width", 80)
    grid = downsample_to_grid(img, grid_width)

    ramp = ascii_cfg.get("ramp", RAMP_DEFAULT)

    # Trim blank rows
    grid = trim_blank_rows(grid, ramp)

    font_family = ascii_cfg.get("font_family", "'Courier New', 'Courier', monospace")
    font_size = ascii_cfg.get("font_size", 8)
    line_height = ascii_cfg.get("line_height", 1.0)
    char_color = ascii_cfg.get("char_color", "#c9d1d9")
    bg_color = ascii_cfg.get("bg_color", "#0d1117")
    typing_speed_ms = ascii_cfg.get("typing_speed_ms", 30)
    cursor_blink_ms = ascii_cfg.get("cursor_blink_ms", 500)

    svg_content = generate_svg(
        grid=grid,
        ramp=ramp,
        font_family=font_family,
        font_size=font_size,
        line_height=line_height,
        char_color=char_color,
        bg_color=bg_color,
        typing_speed_ms=typing_speed_ms,
        cursor_blink_ms=cursor_blink_ms,
    )

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg_content, encoding="utf-8")
    logger.info(f"ASCII SVG written: {out_path.resolve()}")

    if not validate_svg(output_path):
        logger.error("Generated SVG failed validation.")
        return 1

    logger.info("ASCII portrait generation complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
