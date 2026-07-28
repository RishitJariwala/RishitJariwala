"""
README.md generator for animated GitHub profile.

Assembles the profile README from SVG assets using GitHub-supported HTML.
Uses <table> for side-by-side layout and <img> tags for SVG embedding.
All sections are labeled with terminal-style prompts.

Layout:
    ./contributions.sh   [contribution heatmap SVG]
    whoami               [ASCII portrait] [info card]
    cat profile.txt      [info card content shown inline]
    echo $STACK          [tech stack summary]

No JavaScript, no external CSS, no unsupported Markdown.

Usage:
    python scripts/generate_readme.py [--config <path>]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from scripts.utils import load_config, setup_logging, validate_svg

logger = logging.getLogger("generate_readme")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate GitHub profile README.md."
    )
    parser.add_argument(
        "--config", "-c", type=str, default="config.yaml",
        help="Path to configuration file",
    )
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="Output README path (overrides config)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", default=False,
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


def build_terminal_header(username: str) -> str:
    """Build the terminal-style header for the README."""
    return (
        '<div align="center">\n'
        '\n'
        '```ansi\n'
        f'\x1b[1;32m{username}\x1b[0m\x1b[1;37m@\x1b[0m\x1b[1;34mgithub\x1b[0m\x1b[1;37m\x1b[0m\n'
        f'\x1b[1;37m--------------------------\x1b[0m\n'
        '```\n'
        '\n'
    )


def build_footer(username: str) -> str:
    """Build the footer for the README."""
    return (
        '<br>\n'
        '<br>\n'
        '<details>\n'
        '  <summary><code>~ $ echo "Visit my website"</code></summary>\n'
        '\n'
        f'  <a href="https://github.com/{username}">GitHub</a> ·\n'
        '\n'
        '  <br>\n'
        '  <sub><i>README auto-generated with Python + SVG animations</i></sub>\n'
        '</details>\n'
        '\n'
        '</div>\n'
    )


def generate_readme(
    username: str,
    heatmap_path: str,
    portrait_path: str,
    card_path: str,
    heatmap_width: int = 860,
    portrait_width: int = 370,
    card_width: int = 490,
    prompts: Optional[dict] = None,
    spacing: str = "<br>",
) -> str:
    """
    Generate the complete README.md content.

    Layout:
    1. Header with terminal prompt
    2. Contribution heatmap section
    3. Spacing
    4. ASCII portrait + Info card side by side
    5. Footer
    """
    if prompts is None:
        prompts = {}

    sections: list[str] = []
    sections.append(build_terminal_header(username))

    # Contribution heatmap section
    contrib_prompt = prompts.get("contributions", "./contributions.sh")
    sections.append(
        f'  <h3><code>{username}@github ~ $ <span style="color:#56d364">{contrib_prompt}</span></code></h3>\n'
    )
    sections.append(
        f'  <img src="./{heatmap_path}" width="{heatmap_width}" />\n'
    )
    sections.append(f'  {spacing}')

    # ASCII portrait + Info card side by side
    portrait_prompt = prompts.get("portrait", "whoami")
    sections.append(
        f'  <h3><code>{username}@github ~ $ <span style="color:#79c0ff">{portrait_prompt}</span></code></h3>\n'
    )
    sections.append(f'  {spacing}')
    sections.append(
        '  <table>\n'
        '    <tr>\n'
        f'      <td valign="top"><img src="./{portrait_path}" width="{portrait_width}" /></td>\n'
        f'      <td valign="top"><img src="./{card_path}" width="{card_width}" /></td>\n'
        '    </tr>\n'
        '  </table>\n'
    )

    # Tech stack section
    stack_prompt = prompts.get("stack", "echo $STACK")
    stack_data = prompts.get("stack_data", {})
    if stack_data:
        sections.append(f'  {spacing}')
        sections.append(
            f'  <h3><code>{username}@github ~ $ <span style="color:#ff6b6b">{stack_prompt}</span></code></h3>\n'
        )
        sections.append(f'  {spacing}')
        sections.append('  <table>\n')
        for category, items in stack_data.items():
            if items:
                icons = " · ".join(items) if isinstance(items, list) else items
                sections.append(
                    f'    <tr>\n'
                    f'      <td><code>{category}</code></td>\n'
                    f'      <td><code>{icons}</code></td>\n'
                    f'    </tr>\n'
                )
        sections.append('  </table>\n')

    sections.append(build_footer(username))

    return "\n".join(sections)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    setup_logging(level=logging.DEBUG if args.verbose else logging.INFO)

    config = load_config(args.config)
    readme_cfg = config.get("readme", {})
    username = config.get("username", "your-username")

    output_path = args.output or readme_cfg.get("output_path", "README.md")

    heatmap_path = config.get("heatmap", {}).get("output_path", "contrib-heatmap.svg")
    portrait_path = config.get("ascii", {}).get("output_path", "ascii-portrait.svg")
    card_path = config.get("info_card", {}).get("output_path", "info-card.svg")

    heatmap_width = readme_cfg.get("heatmap_width", 860)
    portrait_width = readme_cfg.get("portrait_width", 370)
    card_width = readme_cfg.get("card_width", 490)
    spacing = readme_cfg.get("spacing", "<br>")
    prompts = readme_cfg.get("prompts", {})

    # Validate SVGs exist
    for path, name in [(heatmap_path, "heatmap"), (portrait_path, "portrait"), (card_path, "card")]:
        if not Path(path).exists():
            logger.warning(f"{name} SVG not found: {path}")
        elif not validate_svg(path):
            logger.warning(f"{name} SVG failed validation: {path}")

    # Build stack data from config
    fields = config.get("info_card", {}).get("fields", {})
    stack_data = {
        "Languages": fields.get("languages", []),
        "Frameworks": fields.get("frameworks", []),
        "Tools": fields.get("tools", []),
        "OS": fields.get("os", []),
    }
    prompts = {**prompts, "stack_data": stack_data} if prompts else {"stack_data": stack_data}

    readme_content = generate_readme(
        username=username,
        heatmap_path=heatmap_path,
        portrait_path=portrait_path,
        card_path=card_path,
        heatmap_width=heatmap_width,
        portrait_width=portrait_width,
        card_width=card_width,
        prompts=prompts,
        spacing=spacing,
    )

    out_path = Path(output_path)
    out_path.write_text(readme_content, encoding="utf-8")
    logger.info(f"README written: {out_path.resolve()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
