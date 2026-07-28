"""
Neofetch-style info card SVG generator.

Reads profile information from config.yaml and generates a terminal-inspired
SVG panel. Each row fades/slides in with staggered timing — no looping.

The card auto-sizes based on content length and supports custom colour schemes.

Usage:
    python scripts/make_info_card.py [--config <path>]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Optional, Union

# Ensure project root is on sys.path so scripts package is importable
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from scripts.utils import load_config, setup_logging, validate_svg, file_hash, needs_rebuild

logger = logging.getLogger("make_info_card")

SECTION_ORDER = [
    "name", "title", "location", "company", "website", "email",
    "languages", "frameworks", "tools", "os",
    "interests", "social", "highlights", "current_projects",
]


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate neofetch-style info card SVG."
    )
    parser.add_argument(
        "--config", "-c", type=str, default="config.yaml",
        help="Path to configuration file",
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


def format_value(value: Any) -> list[str]:
    """Format a field value into a list of display lines."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        if all(isinstance(v, dict) for v in value):
            return [f"{list(v.items())[0][0]}: {list(v.items())[0][1]}" for v in value]
        return value
    if isinstance(value, dict):
        return [f"{k}: {v}" for k, v in value.items()]
    return [str(value)]


def generate_info_card_svg(
    fields: dict[str, Any],
    highlights: list[str],
    current_projects: list[str],
    social: dict[str, str],
    font_family: str,
    font_size: int,
    line_height: float,
    title_color: str,
    key_color: str,
    value_color: str,
    symbol_color: str,
    bg_color: str,
    border_color: str,
    row_delay_ms: int,
    fade_duration_ms: int,
    slide_distance: int,
) -> str:
    """
    Generate the neofetch-style SVG info card.

    Layout:
    ┌────────────────────────────────┐
    │  user@github                   │  ← title bar
    │  ---------------------------   │
    │  ● name:   Rishit Jariwala     │  ← info rows (fade + slide in)
    │  ● title:  Software Engineer   │
    │  ● ...                         │
    │                                │
    │  ● highlights:                 │
    │    • Item 1                    │
    │    • Item 2                    │
    │  ---------------------------   │
    │  ● social:                     │
    │    github: rishitjariwala      │
    └────────────────────────────────┘
    """
    char_width = font_size * 0.6
    padding_x = 16
    padding_y = 16
    line_h = int(font_size * line_height)

    # Build display rows
    rows: list[tuple[str, str, str]] = []  # (symbol, key, value)

    for key in SECTION_ORDER:
        if key == "highlights":
            if highlights:
                rows.append(("●", key + ":", ""))
                for h in highlights:
                    rows.append(("", "  •", h))
            continue

        if key == "current_projects":
            if current_projects:
                rows.append(("●", "projects:", ""))
                for p in current_projects:
                    rows.append(("", "  •", p))
            continue

        if key == "social":
            if social:
                rows.append(("●", "social:", ""))
                for platform, handle in social.items():
                    rows.append(("", f"  {platform}:", handle))
            continue

        value = fields.get(key)
        if value is None:
            continue

        formatted = format_value(value)

        if isinstance(value, list) and len(formatted) > 1:
            rows.append(("●", key + ":", ""))
            for item in formatted:
                rows.append(("", "  •", item))
        else:
            label = key.replace("_", " ").title()
            rows.append(("●", label + ":", formatted[0] if formatted else ""))

    # Calculate dimensions
    max_label_width = max((len(label) for _, label, _ in rows), default=0) * char_width
    content_height = len(rows) * line_h
    svg_w = max(400, max_label_width + 200)
    svg_h = padding_y * 2 + content_height + line_h + 20  # + title bar

    lines: list[str] = []
    lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w:.0f}" height="{svg_h:.0f}"')
    lines.append(f'     viewBox="0 0 {svg_w:.0f} {svg_h:.0f}"')
    lines.append(f'     style="background-color:{bg_color}; border: 1px solid {border_color}; border-radius: 8px;">')

    # CSS for animations
    lines.append("  <style>")
    lines.append("    @keyframes fadeSlideIn {")
    lines.append("      from {")
    lines.append("        opacity: 0;")
    lines.append(f"        transform: translateY({slide_distance}px);")
    lines.append("      }")
    lines.append("      to {")
    lines.append("        opacity: 1;")
    lines.append("        transform: translateY(0);")
    lines.append("      }")
    lines.append("    }")
    lines.append("    @keyframes typeIn {")
    lines.append("      from { width: 0; }")
    lines.append("      to { width: 100%; }")
    lines.append("    }")
    lines.append("  </style>")

    # Title bar
    title_y = padding_y + font_size + 4
    lines.append(f'  <text x="{padding_x}" y="{title_y}"')
    lines.append(f'        font-family="{font_family}" font-size="{font_size}"')
    lines.append(f'        fill="{title_color}"')
    lines.append(f'        style="animation: fadeSlideIn {fade_duration_ms}ms ease-out 0ms both;">')
    lines.append(f'    ╭─ user@github ──────────────────────────────────╮')
    lines.append(f'  </text>')

    # Divider under title
    div_y = title_y + 8
    lines.append(f'  <line x1="{padding_x}" y1="{div_y}" x2="{svg_w - padding_x}" y2="{div_y}"')
    lines.append(f'        stroke="{border_color}" stroke-width="1"')
    lines.append(f'        style="animation: fadeSlideIn {fade_duration_ms}ms ease-out 50ms both;" />')

    # Info rows
    for i, (symbol, label, val) in enumerate(rows):
        delay = 100 + i * row_delay_ms
        row_y = div_y + 12 + (i + 1) * line_h

        # Symbol (bullet)
        if symbol:
            lines.append(f'  <text x="{padding_x}" y="{row_y}"')
            lines.append(f'        font-family="{font_family}" font-size="{font_size}"')
            lines.append(f'        fill="{symbol_color}"')
            lines.append(f'        style="animation: fadeSlideIn {fade_duration_ms}ms ease-out {delay}ms both;">')
            lines.append(f'    {symbol}')
            lines.append(f'  </text>')

        # Label
        label_x = padding_x + 18 if symbol else padding_x + 18
        lines.append(f'  <text x="{label_x}" y="{row_y}"')
        lines.append(f'        font-family="{font_family}" font-size="{font_size}"')
        lines.append(f'        fill="{key_color}"')
        lines.append(f'        style="animation: fadeSlideIn {fade_duration_ms}ms ease-out {delay}ms both;">')
        lines.append(f'    {label}')
        lines.append(f'  </text>')

        # Value
        if val:
            val_x = label_x + max_label_width + 12
            lines.append(f'  <text x="{val_x}" y="{row_y}"')
            lines.append(f'        font-family="{font_family}" font-size="{font_size}"')
            lines.append(f'        fill="{value_color}"')
            lines.append(f'        style="animation: fadeSlideIn {fade_duration_ms}ms ease-out {delay + 50}ms both;">')
            lines.append(f'    {val}')
            lines.append(f'  </text>')

    # Bottom border
    bottom_y = rows[-1][2] if any(r[2] for r in rows) else ""
    bottom_line_y = row_y + line_h
    lines.append(f'  <line x1="{padding_x}" y1="{bottom_line_y}" x2="{svg_w - padding_x}" y2="{bottom_line_y}"')
    lines.append(f'        stroke="{border_color}" stroke-width="1"')
    lines.append(f'        style="animation: fadeSlideIn {fade_duration_ms}ms ease-out {100 + len(rows) * row_delay_ms}ms both;" />')

    lines.append("</svg>")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    setup_logging(level=logging.DEBUG if args.verbose else logging.INFO)

    config = load_config(args.config)
    card_cfg = config.get("info_card", {})
    identity = config.get("username", "your-username")

    output_path = args.output or card_cfg.get("output_path", "info-card.svg")

    if not args.force:
        config_hash = file_hash(args.config)
        out_hash = file_hash(output_path)
        if out_hash is not None and config_hash == out_hash:
            logger.info("Info card is up to date. Use --force to rebuild.")
            return 0

    fields = card_cfg.get("fields", {})
    highlights = card_cfg.get("highlights", [])
    current_projects = card_cfg.get("current_projects", [])
    social = card_cfg.get("social", {})

    font_family = card_cfg.get("font_family", "'Courier New', 'Courier', monospace")
    font_size = card_cfg.get("font_size", 13)
    line_height = card_cfg.get("line_height", 1.6)
    title_color = card_cfg.get("title_color", "#ff6b6b")
    key_color = card_cfg.get("key_color", "#79c0ff")
    value_color = card_cfg.get("value_color", "#c9d1d9")
    symbol_color = card_cfg.get("symbol_color", "#56d364")
    bg_color = card_cfg.get("bg_color", "#0d1117")
    border_color = card_cfg.get("border_color", "#30363d")
    anim_cfg = card_cfg.get("animation", {})
    row_delay_ms = anim_cfg.get("row_delay_ms", 100)
    fade_duration_ms = anim_cfg.get("fade_duration_ms", 400)
    slide_distance = anim_cfg.get("slide_distance", 20)

    # Merge top-level identity into fields
    for key in ["name", "title", "location", "company", "website", "email"]:
        if key not in fields and key in config:
            fields[key] = config[key]

    svg_content = generate_info_card_svg(
        fields=fields,
        highlights=highlights,
        current_projects=current_projects,
        social=social,
        font_family=font_family,
        font_size=font_size,
        line_height=line_height,
        title_color=title_color,
        key_color=key_color,
        value_color=value_color,
        symbol_color=symbol_color,
        bg_color=bg_color,
        border_color=border_color,
        row_delay_ms=row_delay_ms,
        fade_duration_ms=fade_duration_ms,
        slide_distance=slide_distance,
    )

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg_content, encoding="utf-8")
    logger.info(f"Info card written: {out_path.resolve()}")

    if not validate_svg(output_path):
        logger.error("Generated SVG failed validation.")
        return 1

    logger.info("Info card generation complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
