"""
Smart rebuild orchestrator for the GitHub Profile README.

Implements change detection (Step 9) to avoid unnecessary regeneration.

Change detection rules:
    - ASCII portrait: rebuild if source image OR ascii config changed
    - Info card: rebuild if config.yaml changed (fields section)
    - Heatmap: always rebuild daily (but check if data file exists)
    - README: rebuild if any SVG or config changed

Usage:
    python scripts/rebuild.py [--config <path>] [--force]
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

from scripts.utils import (
    load_config,
    setup_logging,
    file_hash,
    needs_rebuild,
)

logger = logging.getLogger("rebuild")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smart rebuild orchestrator for profile assets."
    )
    parser.add_argument(
        "--config", "-c", type=str, default="config.yaml",
        help="Path to configuration file",
    )
    parser.add_argument(
        "--force", "-f", action="store_true", default=False,
        help="Force rebuild all assets",
    )
    parser.add_argument(
        "--skip-heatmap", action="store_true", default=False,
        help="Skip heatmap generation (for local use without data)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", default=False,
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


def run_script(script_name: str, args: Optional[list[str]] = None) -> bool:
    """Run a Python script and return True on success."""
    cmd = [sys.executable, f"scripts/{script_name}"]
    if args:
        cmd.extend(args)

    logger.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)
    success = result.returncode == 0

    if not success:
        logger.error(f"Script {script_name} failed with exit code {result.returncode}")
    return success


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    setup_logging(level=logging.DEBUG if args.verbose else logging.INFO)

    config = load_config(args.config)
    ascii_cfg = config.get("ascii", {})

    config_hash = file_hash(args.config)
    logger.info(f"Config hash: {config_hash}")

    force = args.force
    changed = False

    # ── Step 1: Fetch contributions (always) ─────────────────────────────────
    logger.info("─" * 50)
    logger.info("Step 1: Fetching contribution data...")
    if not args.skip_heatmap:
        if run_script("fetch_contributions.py", ["--config", args.config]):
            changed = True
        else:
            logger.warning("Contribution fetch failed, will try to use cached data")
    else:
        logger.info("Skipped (--skip-heatmap)")

    # ── Step 2: Render heatmap ────────────────────────────────────────────────
    logger.info("─" * 50)
    logger.info("Step 2: Rendering heatmap...")
    if not args.skip_heatmap:
        heatmap_args = ["--config", args.config]
        if force:
            heatmap_args.append("--force")
        if run_script("render_heatmap_svg.py", heatmap_args):
            changed = True
    else:
        logger.info("Skipped (--skip-heatmap)")

    # ── Step 3: Generate ASCII portrait (if source changed) ──────────────────
    logger.info("─" * 50)
    logger.info("Step 3: Generating ASCII portrait...")
    source_image = ascii_cfg.get("source_image", "assets/profile-photo.jpg")
    output_portrait = ascii_cfg.get("output_path", "ascii-portrait.svg")

    if force or needs_rebuild(source_image, output_portrait):
        logger.info("ASCII portrait needs rebuild")
        ascii_args = ["--config", args.config]
        if force:
            ascii_args.append("--force")
        if run_script("make_ascii_svg.py", ascii_args):
            changed = True
    else:
        logger.info("ASCII portrait is up to date")

    # ── Step 4: Generate info card (if config changed) ───────────────────────
    logger.info("─" * 50)
    logger.info("Step 4: Generating info card...")
    output_card = config.get("info_card", {}).get("output_path", "info-card.svg")

    if force or needs_rebuild(args.config, output_card):
        logger.info("Info card needs rebuild")
        card_args = ["--config", args.config]
        if force:
            card_args.append("--force")
        if run_script("make_info_card.py", card_args):
            changed = True
    else:
        logger.info("Info card is up to date")

    # ── Step 5: Generate README ──────────────────────────────────────────────
    logger.info("─" * 50)
    logger.info("Step 5: Generating README...")
    output_readme = config.get("readme", {}).get("output_path", "README.md")

    if force or changed or needs_rebuild(args.config, output_readme):
        logger.info("README needs rebuild")
        if run_script("generate_readme.py", ["--config", args.config]):
            changed = True
    else:
        logger.info("README is up to date")

    logger.info("─" * 50)
    if changed:
        logger.info("✅ Profile assets updated successfully!")
    else:
        logger.info("✅ All profile assets are up to date. Nothing changed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
