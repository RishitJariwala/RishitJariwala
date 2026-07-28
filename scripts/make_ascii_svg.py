"""
ASCII portrait SVG generator with self-printing animation.

Converts a processed grayscale image into an animated SVG where each row
types itself in from left to right with a blinking cursor, then freezes.

The conversion pipeline:
    1. Load grayscale image
    2. Downsample to character grid
    3. Map each pixel brightness to a glyph from a density ramp
    4. Generate SVG with SMIL/CSS animations for typing effect

Usage:
    python scripts/make_ascii_svg.py [--config <path>]
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from scripts.utils import load_config, setup_logging, validate_svg, file_hash, needs_rebuild

logger = logging.getLogger("make_ascii_svg")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate animated ASCII portrait SVG from processed photo."
    )
    parser.add_argument(
        "--config", "-c", type=str, default="config.yaml",
        help="Path to configuration file",
    )
    parser.add_argument(
        "--input", "-i", type=str, default=None,
        help="Input grayscale PNG (overrides config)",
    )
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="Output SVG path (overrides config)",
    )
    parser.add_argument(
        "--force", "-f", action="store_true", default=False,
        help="Force regeneration even if output exists",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", default=False,
        help="Enable debug logging",
    )
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
    """Resize image to target character grid width, preserving aspect ratio."""
    h, w = img.shape
    aspect = h / w
    grid_height = max(1, int(grid_width * aspect * 0.45))  # 0.45 accounts for font aspect (char width < height)
    resized = cv2.resize(img, (grid_width, grid_height), interpolation=cv2.INTER_AREA)
    logger.info(f"Grid size: {resized.shape[1]}x{resized.shape[0]} characters")
    return resized


def pixel_to_glyph(pixel_value: int, ramp: str) -> str:
    """
    Map a grayscale pixel (0=black, 255=white) to a glyph from the density ramp.

    The ramp is ordered from sparse (low density, for bright areas) to dense
    (high density, for dark areas). A leading space clears background.
    """
    if not ramp:
        return " "
    # Invert: bright pixels → sparse chars, dark pixels → dense chars
    inverted = 255 - pixel_value
    index = int(inverted / 255.0 * (len(ramp) - 1))
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
    Generate an animated SVG of the ASCII art.

    Each row is clipped horizontally and revealed left-to-right with a
    blinking cursor at the writing edge. Rows are staggered top-to-bottom.
    Animation plays once then freezes.

    The technique:
    - Each row uses an SVG <clipPath> that expands from 0 to full width
    - A <rect> cursor blinks at the clip edge
    - SMIL <animate> drives the clip expansion
    - Staggered begin times create the top-to-bottom typing effect
    """
    rows, cols = grid.shape
    char_w = font_size * 0.6   # approximate monospace character width
    char_h = font_size * line_height
    svg_w = cols * char_w
    svg_h = rows * char_h
    padding = 5

    # Build the glyph map
    glyph_rows: list[list[str]] = []
    for r in range(rows):
        row_glyphs: list[str] = []
        for c in range(cols):
            pixel = int(grid[r, c])
            glyph = pixel_to_glyph(pixel, ramp)
            row_glyphs.append(glyph)
        glyph_rows.append(row_glyphs)

    svg_w_total = svg_w + 2 * padding
    svg_h_total = svg_h + 2 * padding + char_h  # extra space for cursor

    lines: list[str] = []
    lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w_total:.0f}" height="{svg_h_total:.0f}"')
    lines.append(f'     viewBox="0 0 {svg_w_total:.0f} {svg_h_total:.0f}"')
    lines.append(f'     style="background-color:{bg_color};">')

    # CSS keyframes for cursor blink
    lines.append("  <style>")
    lines.append("    @keyframes blink {")
    lines.append("      0%, 49% { opacity: 1; }")
    lines.append("      50%, 100% { opacity: 0; }")
    lines.append("    }")
    lines.append("    @keyframes fadeIn {")
    lines.append("      from { opacity: 0; }")
    lines.append("      to   { opacity: 1; }")
    lines.append("    }")
    lines.append("  </style>")

    # Defs for clip paths
    lines.append("  <defs>")

    for r in range(rows):
        row_text = "".join(glyph_rows[r])
        # Escape XML special characters
        row_text = (row_text.replace("&", "&amp;")
                            .replace("<", "&lt;")
                            .replace(">", "&gt;")
                            .replace('"', "&quot;"))

        width_px = len(row_text) * char_w
        duration_ms = len(row_text) * typing_speed_ms
        delay_ms = r * 80  # stagger between rows

        # Clip path for this row
        lines.append(f'    <clipPath id="row-clip-{r}">')
        lines.append(f'      <rect x="{padding}" y="{padding + r * char_h}"')
        lines.append(f'            width="0" height="{char_h}">')
        lines.append(f'        <animate attributeName="width"')
        lines.append(f'                 from="0" to="{width_px}"')
        lines.append(f'                 dur="{duration_ms}ms" begin="{delay_ms}ms"')
        lines.append(f'                 fill="freeze" />')
        lines.append(f'      </rect>')
        lines.append(f'    </clipPath>')
    lines.append("  </defs>")

    # Rendering area
    for r in range(rows):
        row_text = "".join(glyph_rows[r])
        row_text = (row_text.replace("&", "&amp;")
                            .replace("<", "&lt;")
                            .replace(">", "&gt;")
                            .replace('"', "&quot;"))

        width_px = len(row_text) * char_w
        duration_ms = len(row_text) * typing_speed_ms
        delay_ms = r * 80
        cursor_delay_ms = delay_ms + duration_ms

        # Row text (clipped)
        lines.append(f'  <text x="{padding}" y="{padding + r * char_h + font_size * 0.85}"')
        lines.append(f'        font-family="{font_family}" font-size="{font_size}"')
        lines.append(f'        fill="{char_color}"')
        lines.append(f'        clip-path="url(#row-clip-{r})">')
        lines.append(f'    {row_text}')
        lines.append(f'  </text>')

        # Blinking cursor
        cursor_x = padding + width_px + 1
        lines.append(f'  <rect x="{cursor_x}" y="{padding + r * char_h + 1}"')
        lines.append(f'        width="{max(1, font_size * 0.4)}" height="{char_h - 2}"')
        lines.append(f'        fill="{char_color}"')
        lines.append(f'        style="animation: blink {cursor_blink_ms}ms step-end {'infinite' if r == rows - 1 else '2'};')
        lines.append(f'                      animation-delay: {cursor_delay_ms}ms;">')
        lines.append(f'  </rect>')

    # Label: blinking cursor line at bottom
    total_duration = rows * 80 + max(len(r) for r in glyph_rows) * typing_speed_ms
    label_y = padding + rows * char_h + font_size + 4
    lines.append(f'  <text x="{padding}" y="{label_y}"')
    lines.append(f'        font-family="{font_family}" font-size="{font_size * 0.8}"')
    lines.append(f'        fill="{char_color}"')
    lines.append(f'        style="animation: fadeIn 500ms ease-out {total_duration}ms both;">')
    lines.append(f'    █')
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

    # Check if rebuild is needed
    if not args.force:
        if not needs_rebuild(input_path, output_path):
            logger.info("ASCII portrait is up to date. Use --force to rebuild.")
            return 0

    try:
        img = load_grayscale(input_path)
    except (FileNotFoundError, ValueError) as exc:
        logger.error(str(exc))
        return 1

    grid_width = ascii_cfg.get("width", 80)
    grid = downsample_to_grid(img, grid_width)

    ramp = ascii_cfg.get("ramp", " .`:-=+*cs#%@")
    font_family = ascii_cfg.get("font_family", "Courier New, Courier, monospace")
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
