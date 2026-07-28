"""
GitHub contribution data fetcher.

Downloads public contribution data from GitHub's HTML endpoint:
    https://github.com/users/<username>/contributions

Parses the HTML with BeautifulSoup, extracts daily contribution counts,
and computes derived statistics (streaks, totals, averages).

No authentication is required. Uses only public GitHub data.

Usage:
    python scripts/fetch_contributions.py [--config <path>]
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, date, timezone
from pathlib import Path
from typing import Any, Optional

# Ensure project root is on sys.path so scripts package is importable
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests
from bs4 import BeautifulSoup

from scripts.utils import load_config, setup_logging, save_json, load_json, validate_json_structure

logger = logging.getLogger("fetch_contributions")

REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch GitHub contribution data."
    )
    parser.add_argument(
        "--config", "-c", type=str, default="config.yaml",
        help="Path to configuration file",
    )
    parser.add_argument(
        "--username", "-u", type=str, default=None,
        help="GitHub username (overrides config)",
    )
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="Output JSON path (overrides config)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", default=False,
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


def fetch_contributions_html(username: str, retries: int = MAX_RETRIES) -> str:
    """
    Fetch the contribution HTML fragment from GitHub.

    URL: https://github.com/users/<username>/contributions

    This endpoint returns HTML that GitHub uses to render the
    contribution graph on profile pages.
    """
    url = f"https://github.com/users/{username}/contributions"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ProfileBot/1.0)",
        "Accept": "text/html",
    }

    last_error: Optional[Exception] = None
    for attempt in range(retries):
        try:
            logger.info(f"Fetching contributions for @{username} (attempt {attempt + 1})")
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            last_error = exc
            logger.warning(f"Request failed (attempt {attempt + 1}): {exc}")
            if attempt < retries - 1:
                import time
                time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))

    raise ConnectionError(f"Failed to fetch contributions after {retries} retries: {last_error}")


def parse_total_from_html(soup: BeautifulSoup) -> int:
    """Extract total contribution count from the h2 element."""
    h2 = soup.find("h2", id="js-contribution-activity-description")
    if h2:
        text = h2.get_text(strip=True)
        parts = text.split()
        if parts and parts[0].isdigit():
            return int(parts[0])
    return 0


def estimate_day_counts(
    days: list[dict[str, Any]],
    total: int,
) -> list[dict[str, Any]]:
    """Estimate per-day contribution counts from data-level and total.

    GitHub's HTML now only exposes data-level (0-4), not exact counts.
    This function distributes the total across days proportional to level.
    """
    if not days or total == 0:
        for d in days:
            d["count"] = 0
        return days

    # Group days by level
    level_groups: dict[int, list[dict[str, Any]]] = {}
    for d in days:
        level = d.get("level", 0)
        if level not in level_groups:
            level_groups[level] = []
        level_groups[level].append(d)

    # Weight by level (level 1 = 1, level 2 = 3, level 3 = 6, level 4 = 10)
    level_weights = {0: 0, 1: 1, 2: 3, 3: 6, 4: 10}
    total_weight = sum(
        level_weights.get(level, 0) * len(days_list)
        for level, days_list in level_groups.items()
    )

    if total_weight == 0:
        return days

    # Distribute total proportionally
    for d in days:
        level = d.get("level", 0)
        weight = level_weights.get(level, 0)
        if weight > 0 and total_weight > 0:
            d["count"] = max(1, round(total * weight / total_weight))
        else:
            d["count"] = 0

    # Adjust to match exact total
    assigned = sum(d["count"] for d in days)
    diff = total - assigned
    if diff != 0 and len(days) > 0:
        # Add/subtract difference from highest-level days
        sorted_by_level = sorted(days, key=lambda d: d["level"], reverse=True)
        for i in range(abs(diff)):
            idx = i % len(sorted_by_level)
            sorted_by_level[idx]["count"] = max(0, sorted_by_level[idx]["count"] + (1 if diff > 0 else -1))

    return days


def parse_contributions(html: str) -> tuple[list[dict[str, Any]], list[list[Optional[dict[str, Any]]]]]:
    """
    Parse the contribution HTML into structured data.

    GitHub's current contribution graph HTML uses a <table> with <td> elements
    containing data-date and data-level attributes. Exact counts are not
    included per-cell; only the total is available from the <h2> element.

    Returns (days, weeks) where weeks is a 53x7 grid.
    """
    soup = BeautifulSoup(html, "html.parser")
    days: list[dict[str, Any]] = []
    weeks: list[list[Optional[dict[str, Any]]]] = []

    total = parse_total_from_html(soup)

    # Find the contribution table
    table = soup.find("table")
    if table is None:
        # Try the newer SVG-based layout
        days = parse_contribution_svg(soup)
        days = estimate_day_counts(days, total)
        return days, []

    tbody = table.find("tbody")
    if tbody is None:
        raise ValueError("Could not find contribution table body")

    for tr in tbody.find_all("tr"):
        week: list[Optional[dict[str, Any]]] = []
        for td in tr.find_all("td"):
            date_str = td.get("data-date", "")
            level_str = td.get("data-level", "0")
            level = int(level_str) if level_str.isdigit() else 0

            day_data: dict[str, Any] = {
                "date": date_str,
                "count": 0,
                "level": level,
                "weekday": 0,
            }
            week.append(day_data)
            if date_str:
                days.append(day_data)

        if week:
            weeks.append(week)

    days = estimate_day_counts(days, total)
    return days, weeks


def parse_contribution_svg(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """
    Fallback parser for the SVG-based contribution graph layout.

    GitHub may serve an SVG <svg> with <rect> elements instead of a table.
    Each <rect> has data-date and data-level attributes.
    """
    days: list[dict[str, Any]] = []
    svg = soup.find("svg")
    if svg is None:
        raise ValueError("Could not find contribution data (no table or SVG)")

    for rect in svg.find_all("rect"):
        date_str = rect.get("data-date", "")
        level_str = rect.get("data-level", "0")
        level = int(level_str) if level_str.isdigit() else 0
        count = 0

        # Try to get count from aria-label
        aria_label = rect.get("aria-label", "")
        if aria_label:
            parts = aria_label.split()
            if parts and parts[0].isdigit():
                count = int(parts[0])

        day_data = {
            "date": date_str,
            "count": count,
            "level": level,
            "weekday": 0,
        }
        if date_str:
            days.append(day_data)

    return days


def compute_statistics(days: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute derived statistics from daily contribution data.

    Calculates:
    - current_streak: consecutive days up to today with count > 0
    - longest_streak: longest run of consecutive active days
    - yearly_total: total contributions in the dataset
    - monthly_totals: breakdown by month
    - best_day: day with highest contribution count
    - average_daily: mean contributions per day
    - active_days: days with count > 0
    - inactive_days: days with count == 0
    """
    if not days:
        return {
            "current_streak": 0,
            "longest_streak": 0,
            "yearly_total": 0,
            "monthly_totals": {},
            "best_day": None,
            "average_daily": 0.0,
            "active_days": 0,
            "inactive_days": 0,
        }

    # Sort by date
    sorted_days = sorted(days, key=lambda d: d["date"])

    yearly_total = sum(d["count"] for d in sorted_days)
    active_days = sum(1 for d in sorted_days if d["count"] > 0)
    inactive_days = len(sorted_days) - active_days
    average_daily = round(yearly_total / len(sorted_days), 1) if sorted_days else 0

    # Best day
    best_day = max(sorted_days, key=lambda d: d["count"])
    best_day = best_day if best_day["count"] > 0 else None

    # Monthly totals
    monthly_totals: dict[str, int] = {}
    for d in sorted_days:
        month_key = d["date"][:7]  # YYYY-MM
        monthly_totals[month_key] = monthly_totals.get(month_key, 0) + d["count"]

    # Streaks
    current_streak = 0
    longest_streak = 0
    running_streak = 0

    today = date.today()
    for d in sorted_days:
        if d["count"] > 0:
            running_streak += 1
            longest_streak = max(longest_streak, running_streak)

            # Check if this is part of the current streak (working backwards from today)
            day_date = datetime.strptime(d["date"], "%Y-%m-%d").date()
            if day_date <= today:
                current_streak = running_streak
        else:
            # Reset
            if running_streak > 0:
                pass
            running_streak = 0

    # Proper current streak calculation (from today backwards)
    current_streak = 0
    for d in reversed(sorted_days):
        day_date = datetime.strptime(d["date"], "%Y-%m-%d").date()
        if day_date > today:
            continue
        if d["count"] > 0:
            current_streak += 1
        else:
            break

    return {
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "yearly_total": yearly_total,
        "monthly_totals": monthly_totals,
        "best_day": best_day,
        "average_daily": average_daily,
        "active_days": active_days,
        "inactive_days": inactive_days,
    }


def build_week_grid(days: list[dict[str, Any]]) -> list[list[Optional[dict[str, Any]]]]:
    """
    Build a 53x7 grid of days organised by week.

    Each week starts on Sunday (weekday=0).
    """
    if not days:
        return []

    sorted_days = sorted(days, key=lambda d: d["date"])

    # Group by ISO week
    weeks_dict: dict[str, list[dict[str, Any]]] = {}
    for d in sorted_days:
        day_date = datetime.strptime(d["date"], "%Y-%m-%d").date()
        iso_year, iso_week, iso_weekday = day_date.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        d["weekday"] = iso_weekday % 7  # 0 = Sunday (GitHub style)
        if week_key not in weeks_dict:
            weeks_dict[week_key] = []
        weeks_dict[week_key].append(d)

    # Build grid
    grid: list[list[Optional[dict[str, Any]]]] = []
    for week_key in sorted(weeks_dict.keys()):
        week_days = weeks_dict[week_key]
        week_grid: list[Optional[dict[str, Any]]] = [None] * 7
        for d in week_days:
            weekday = d["weekday"]
            if 0 <= weekday <= 6:
                week_grid[weekday] = d
        grid.append(week_grid)

    return grid


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    setup_logging(level=logging.DEBUG if args.verbose else logging.INFO)

    config = load_config(args.config)
    username = args.username or config.get("username", "")
    if not username:
        logger.error("No username specified. Set in config.yaml or use --username.")
        return 1

    data_path = args.output or config.get("heatmap", {}).get("data_path", "data/contributions.json")

    try:
        html = fetch_contributions_html(username)
    except (ConnectionError, requests.RequestException) as exc:
        logger.error(f"Failed to fetch contributions: {exc}")
        return 1

    try:
        days, weeks = parse_contributions(html)
    except ValueError as exc:
        logger.error(f"Failed to parse contributions: {exc}")
        return 1

    if not days:
        logger.warning("No contribution data found.")
        days = []
        weeks = []

    stats = compute_statistics(days)
    week_grid = build_week_grid(days)

    result = {
        "username": username,
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "days": days,
        "weeks": week_grid,
        **stats,
    }

    save_json(result, data_path)
    logger.info(f"Saved contribution data: {Path(data_path).resolve()}")
    logger.info(f"  Contributions: {stats['yearly_total']}")
    logger.info(f"  Active days: {stats['active_days']}")
    logger.info(f"  Current streak: {stats['current_streak']}")
    logger.info(f"  Longest streak: {stats['longest_streak']}")
    logger.info(f"  Best day: {stats['best_day']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
