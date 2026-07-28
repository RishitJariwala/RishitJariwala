"""
Shared utility functions for the GitHub Profile README Generator.

Provides configuration loading, logging setup, file hashing for change
detection, and SVG validation — used by every script in the project.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

import yaml

from scripts.type_defs import ConfigDict


def setup_logging(level: int = logging.INFO) -> None:
    """Configure a root logger with a consistent format."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )


def load_config(path: str = "config.yaml") -> ConfigDict:
    """
    Load YAML configuration from disk.

    Returns an empty dict if the file does not exist (graceful fallback).
    """
    config_path = Path(path)
    if not config_path.exists():
        logging.getLogger("utils").warning(f"Config not found at {path}, using defaults")
        return {}
    with open(config_path, "r") as f:
        return yaml.safe_load(f) or {}


def save_json(data: Any, path: str) -> None:
    """Write data as JSON to disk with human-readable formatting."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(data, f, indent=2, default=str)
    logging.getLogger("utils").debug(f"Wrote JSON: {out}")


def load_json(path: str) -> Any:
    """Load JSON from disk. Returns None on failure."""
    p = Path(path)
    if not p.exists():
        return None
    with open(p, "r") as f:
        return json.load(f)


def file_hash(path: str) -> Optional[str]:
    """
    Compute SHA-256 hash of a file for change detection.

    Returns None if the file does not exist.
    """
    p = Path(path)
    if not p.exists():
        return None
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def needs_rebuild(source_path: str, output_path: str) -> bool:
    """
    Check if an output asset needs to be rebuilt.

    Returns True if:
    - Output does not exist
    - Source is newer than output
    - Source hash changed (if a hash file exists)

    This is the core of the smart rebuild system (Step 9).
    """
    src = Path(source_path)
    out = Path(output_path)

    if not out.exists():
        return True

    if not src.exists():
        return False

    src_mtime = os.path.getmtime(src)
    out_mtime = os.path.getmtime(out)
    return src_mtime > out_mtime


def validate_svg(path: str) -> bool:
    """
    Validate that a file is a well-formed SVG.

    Checks for:
    - File existence
    - Correct XML declaration or <svg> tag
    - Closing </svg> tag
    - Non-zero file size

    Returns True if valid.
    """
    p = Path(path)
    if not p.exists():
        logging.getLogger("utils").error(f"SVG validation failed: file not found — {path}")
        return False

    if p.stat().st_size == 0:
        logging.getLogger("utils").error(f"SVG validation failed: empty file — {path}")
        return False

    content = p.read_text(encoding="utf-8")

    if not re.search(r'<svg\b', content, re.IGNORECASE):
        logging.getLogger("utils").error(f"SVG validation failed: no <svg> tag — {path}")
        return False

    if not re.search(r'</svg\s*>', content, re.IGNORECASE):
        logging.getLogger("utils").error(f"SVG validation failed: no </svg> tag — {path}")
        return False

    return True


def validate_json_structure(data: Any, required_keys: list[str]) -> bool:
    """
    Validate that a JSON object contains all required keys.

    Performs recursive key presence checking for nested dicts.
    """
    if not isinstance(data, dict):
        return False
    for key in required_keys:
        if key not in data:
            return False
    return True
