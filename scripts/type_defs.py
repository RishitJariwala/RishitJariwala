"""
Type definitions for the GitHub Profile README Generator.

Provides typed dicts and type aliases used across all scripts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

ConfigDict = Dict[str, Any]


class ContributionDay(TypedDict):
    """A single day's contribution data."""
    date: str
    count: int
    level: int
    weekday: int


class ContributionData(TypedDict):
    """Full contribution dataset."""
    days: List[ContributionDay]
    current_streak: int
    longest_streak: int
    yearly_total: int
    monthly_totals: Dict[str, int]
    best_day: Optional[ContributionDay]
    average_daily: float
    active_days: int
    inactive_days: int
    weeks: List[List[Optional[ContributionDay]]]


class ASCIIConfig(TypedDict):
    source_image: str
    output_path: str
    width: int
    ramp: str
    font_family: str
    font_size: int
    line_height: float
    typing_speed_ms: int
    cursor_blink_ms: int
    char_color: str
    bg_color: str


class HeatmapConfig(TypedDict):
    output_path: str
    data_path: str
    cell_size: int
    cell_spacing: int
    cell_radius: int
    weeks: int
    days: int
    animation_duration_ms: int
    diagonal_delay_ms: int
    palette: List[str]
    label_color: str
    stat_color: str
    bg_color: str


class InfoCardConfig(TypedDict):
    output_path: str
    font_family: str
    font_size: int
    line_height: float
    title_color: str
    key_color: str
    value_color: str
    symbol_color: str
    bg_color: str
    border_color: str
    animation: Dict[str, Any]
    fields: Dict[str, Any]
    highlights: List[str]
    current_projects: List[str]
    social: Dict[str, str]
