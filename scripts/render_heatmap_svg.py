"""
Contribution heatmap SVG renderer.

Reads contribution data from JSON (produced by fetch_contributions.py) and
renders a GitHub-style 53-week contribution graph as an animated SVG.

The heatmap reveals itself with a diagonal box-by-box animation.
Each cell slides in from above, staggered by week + day position.
Animation plays once then freezes.

Usage:
    python scripts/render_heatmap_svg.py [--config <path>]
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from scripts.utils import (
    load_config,
    setup_logging,
    save_json,
    load_json,
    validate_svg,
    validate_json_structure,
)

logger = logging.getLogger("render_heatmap")

MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WEEKDAY_LABELS = ["Mon", "", "Wed", "", "Fri", "", ""]


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render contribution heatmap SVG."
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
        "--data", "-d", type=str, default=None,
        help="Input JSON data path (overrides config)",
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


def get_month_labels(weeks: list[list[Optional[dict[str, Any]]]]) -> list[tuple[int, str]]:
    """Extract month label positions from the week grid."""
    labels: list[tuple[int, str]] = []
    last_month = -1
    for week_idx, week in enumerate(weeks):
        for day in week:
            if day is None or not day.get("date"):
                continue
            try:
                dt = datetime.strptime(day["date"], "%Y-%m-%d")
                if dt.month != last_month:
                    last_month = dt.month
                    labels.append((week_idx, MONTH_LABELS[dt.month - 1]))
                    break
            except (ValueError, IndexError):
                continue
    return labels


def generate_heatmap_svg(
    data: dict[str, Any],
    cell_size: int,
    cell_spacing: int,
    cell_radius: int,
    palette: list[str],
    label_color: str,
    stat_color: str,
    bg_color: str,
    anim_duration_ms: int,
    diagonal_delay_ms: int,
) -> str:
    """
    Generate the contribution heatmap SVG.

    Layout (GitHub style):
    ┌──────────────────────────────────────────────┐
    │  Jan  Feb  Mar  Apr ...                      │  ← month labels
    │  Mon ┌──┐┌──┐┌──┐┌──┐┌──┐┌──┐┌──┐          │
    │  Wed │  ││  ││  ││  ││  ││  ││  │          │  ← contribution cells
    │  Fri └──┘└──┘└──┘└──┘└──┘└──┘└──┘          │
    │  Less  ■ ■ ■ ■ ■  More                      │  ← legend
    │  9,376 contributions in the last year        │  ← footer stats
    └──────────────────────────────────────────────┘

    Animation: diagonal reveal — each cell fades + slides from top,
    staggered by (week + day) * diagonal_delay_ms.
    """
    weeks = data.get("weeks", [])
    if not weeks:
        weeks = build_weeks_from_days(data.get("days", []))

    stats = {
        "yearly_total": data.get("yearly_total", 0),
        "current_streak": data.get("current_streak", 0),
        "longest_streak": data.get("longest_streak", 0),
        "average_daily": data.get("average_daily", 0),
        "active_days": data.get("active_days", 0),
        "best_day": data.get("best_day"),
    }

    step = cell_size + cell_spacing
    label_width = 32
    header_height = 20
    footer_height = 40
    legend_height = 20
    padding_x = 10
    padding_y = 10

    graph_w = len(weeks) * step + label_width
    graph_h = 7 * step
    total_w = graph_w + padding_x * 2
    total_h = graph_h + header_height + legend_height + footer_height + padding_y * 3

    month_labels = get_month_labels(weeks)

    lines: list[str] = []
    lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:.0f}" height="{total_h:.0f}"')
    lines.append(f'     viewBox="0 0 {total_w:.0f} {total_h:.0f}"')
    lines.append(f'     style="background-color:{bg_color};">')

    # CSS keyframes
    lines.append("  <style>")
    lines.append("    @keyframes cellReveal {")
    lines.append("      from {")
    lines.append("        opacity: 0;")
    lines.append("        transform: translateY(-8px);")
    lines.append("      }")
    lines.append("      to {")
    lines.append("        opacity: 1;")
    lines.append("        transform: translateY(0);")
    lines.append("      }")
    lines.append("    }")
    lines.append("    @keyframes fadeIn {")
    lines.append("      from { opacity: 0; }")
    lines.append("      to   { opacity: 1; }")
    lines.append("    }")
    lines.append("  </style>")

    # Month labels
    for week_idx, label in month_labels:
        x = padding_x + label_width + week_idx * step + step / 2
        lines.append(f'  <text x="{x:.0f}" y="{padding_y + header_height - 6}"')
        lines.append(f'        font-family="\'Courier New\', Courier, monospace" font-size="{max(9, cell_size - 1)}"')
        lines.append(f'        fill="{label_color}" text-anchor="start"')
        lines.append(f'        style="animation: fadeIn 300ms ease-out {(week_idx * diagonal_delay_ms)}ms both;">')
        lines.append(f'    {label}')
        lines.append(f'  </text>')

    # Weekday labels
    for day_idx, label in enumerate(WEEKDAY_LABELS):
        if not label:
            continue
        y = padding_y + header_height + day_idx * step + step * 0.75
        lines.append(f'  <text x="{padding_x}" y="{y:.0f}"')
        lines.append(f'        font-family="\'Courier New\', Courier, monospace" font-size="{max(9, cell_size - 1)}"')
        lines.append(f'        fill="{label_color}" text-anchor="end"')
        lines.append(f'        style="animation: fadeIn 300ms ease-out {day_idx * 50}ms both;">')
        lines.append(f'    {label}')
        lines.append(f'  </text>')

    # Contribution cells
    for week_idx, week in enumerate(weeks):
        for day_idx in range(7):
            day = week[day_idx] if day_idx < len(week) else None
            level = day.get("level", 0) if day else 0
            count = day.get("count", 0) if day else 0

            level = min(level, len(palette) - 1)
            color = palette[level]

            x = padding_x + label_width + week_idx * step + cell_spacing / 2
            y = padding_y + header_height + day_idx * step + cell_spacing / 2

            delay = (week_idx + day_idx) * diagonal_delay_ms
            duration = min(anim_duration_ms, 600)

            lines.append(f'  <rect x="{x:.0f}" y="{y:.0f}"')
            lines.append(f'        width="{cell_size}" height="{cell_size}"')
            lines.append(f'        rx="{cell_radius}" ry="{cell_radius}"')
            lines.append(f'        fill="{color}"')
            lines.append(f'        style="animation: cellReveal {duration}ms ease-out {delay}ms both;" />')

    # Legend
    legend_y = padding_y + header_height + graph_h + 10
    legend_x = padding_x + label_width
    lines.append(f'  <text x="{legend_x:.0f}" y="{legend_y:.0f}"')
    lines.append(f'        font-family="\'Courier New\', Courier, monospace" font-size="{max(9, cell_size - 2)}"')
    lines.append(f'        fill="{label_color}"')
    lines.append(f'        style="animation: fadeIn 500ms ease-out {len(weeks) * diagonal_delay_ms}ms both;">')
    lines.append(f'    Less')
    lines.append(f'  </text>')

    for i, color in enumerate(palette):
        lx = legend_x + 46 + i * (cell_size + 4)
        lines.append(f'  <rect x="{lx:.0f}" y="{legend_y - cell_size + 2}"')
        lines.append(f'        width="{cell_size}" height="{cell_size}"')
        lines.append(f'        rx="{cell_radius}" ry="{cell_radius}"')
        lines.append(f'        fill="{color}"')
        lines.append(f'        style="animation: fadeIn 500ms ease-out {len(weeks) * diagonal_delay_ms + i * 50}ms both;" />')

    lines.append(f'  <text x="{legend_x + 46 + len(palette) * (cell_size + 4):.0f}" y="{legend_y:.0f}"')
    lines.append(f'        font-family="\'Courier New\', Courier, monospace" font-size="{max(9, cell_size - 2)}"')
    lines.append(f'        fill="{label_color}"')
    lines.append(f'        style="animation: fadeIn 500ms ease-out {len(weeks) * diagonal_delay_ms + len(palette) * 50}ms both;">')
    lines.append(f'    More')
    lines.append(f'  </text>')

    # Footer statistics
    footer_y = legend_y + 24
    yearly_total = stats["yearly_total"]
    lines.append(f'  <text x="{padding_x + label_width:.0f}" y="{footer_y:.0f}"')
    lines.append(f'        font-family="\'Courier New\', Courier, monospace" font-size="{max(10, cell_size)}"')
    lines.append(f'        fill="{stat_color}"')
    lines.append(f'        style="animation: fadeIn 500ms ease-out {len(weeks) * diagonal_delay_ms + 200}ms both;">')
    lines.append(f'    {yearly_total:,} contributions in the last year')
    lines.append(f'  </text>')

    streak_text = f"Current streak: {stats['current_streak']}d  |  Longest streak: {stats['longest_streak']}d"
    lines.append(f'  <text x="{padding_x + label_width:.0f}" y="{footer_y + 18:.0f}"')
    lines.append(f'        font-family="\'Courier New\', Courier, monospace" font-size="{max(9, cell_size - 1)}"')
    lines.append(f'        fill="{label_color}"')
    lines.append(f'        style="animation: fadeIn 500ms ease-out {len(weeks) * diagonal_delay_ms + 300}ms both;">')
    lines.append(f'    {streak_text}')
    lines.append(f'  </text>')

    lines.append("</svg>")
    return "\n".join(lines)


def build_weeks_from_days(days: list[dict[str, Any]]) -> list[list[Optional[dict[str, Any]]]]:
    """Build a week grid from a flat list of days."""
    if not days:
        return []
    sorted_days = sorted(days, key=lambda d: d.get("date", ""))
    weeks_dict: dict[str, list[dict[str, Any]]] = {}
    for d in sorted_days:
        date_str = d.get("date", "")
        if not date_str:
            continue
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            iso_year, iso_week, iso_weekday = dt.isocalendar()
            week_key = f"{iso_year}-W{iso_week:02d}"
            d["weekday"] = iso_weekday % 7
            if week_key not in weeks_dict:
                weeks_dict[week_key] = []
            weeks_dict[week_key].append(d)
        except ValueError:
            continue

    grid: list[list[Optional[dict[str, Any]]]] = []
    for week_key in sorted(weeks_dict.keys()):
        week_days = weeks_dict[week_key]
        week_grid: list[Optional[dict[str, Any]]] = [None] * 7
        for d in week_days:
            wd = d.get("weekday", 0)
            if 0 <= wd <= 6:
                week_grid[wd] = d
        grid.append(week_grid)
    return grid


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    setup_logging(level=logging.DEBUG if args.verbose else logging.INFO)

    config = load_config(args.config)
    heatmap_cfg = config.get("heatmap", {})

    data_path = args.data or heatmap_cfg.get("data_path", "data/contributions.json")
    output_path = args.output or heatmap_cfg.get("output_path", "contrib-heatmap.svg")

    data = load_json(data_path)
    if data is None:
        logger.error(f"No contribution data found at {data_path}.")
        logger.error("Run fetch_contributions.py first.")
        return 1

    cell_size = heatmap_cfg.get("cell_size", 13)
    cell_spacing = heatmap_cfg.get("cell_spacing", 3)
    cell_radius = heatmap_cfg.get("cell_radius", 3)
    palette = heatmap_cfg.get("palette", ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"])
    label_color = heatmap_cfg.get("label_color", "#8b949e")
    stat_color = heatmap_cfg.get("stat_color", "#c9d1d9")
    bg_color = heatmap_cfg.get("bg_color", "#0d1117")
    anim_duration_ms = heatmap_cfg.get("animation_duration_ms", 800)
    diagonal_delay_ms = heatmap_cfg.get("diagonal_delay_ms", 5)

    svg_content = generate_heatmap_svg(
        data=data,
        cell_size=cell_size,
        cell_spacing=cell_spacing,
        cell_radius=cell_radius,
        palette=palette,
        label_color=label_color,
        stat_color=stat_color,
        bg_color=bg_color,
        anim_duration_ms=anim_duration_ms,
        diagonal_delay_ms=diagonal_delay_ms,
    )

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg_content, encoding="utf-8")
    logger.info(f"Heatmap SVG written: {out_path.resolve()}")

    if not validate_svg(output_path):
        logger.error("Generated SVG failed validation.")
        return 1

    logger.info("Heatmap generation complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
