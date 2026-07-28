"""
Photo preparation pipeline for ASCII portrait generation.

Takes a source photograph and processes it into a high-contrast grayscale
image optimised for ASCII art conversion. The pipeline:

    1. Removes background (via rembg) so only the subject remains
    2. Applies CLAHE for local contrast enhancement
    3. Adjusts brightness, contrast, and gamma
    4. Composites onto pure white background
    5. Exports as grayscale PNG

Usage:
    python scripts/prep_photo.py [--input <path>] [--config <path>]

Configuration is read from config.yaml by default, but all processing
parameters can be overridden via command-line arguments.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

try:
    from rembg import remove as remove_bg
    HAS_REMBG = True
except ImportError:
    HAS_REMBG = False

from scripts.utils import load_config, setup_logging

logger = logging.getLogger("prep_photo")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a photo for ASCII portrait generation."
    )
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default=None,
        help="Path to source photo (overrides config.yaml)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output path for prepped image (default: assets/source-prepped.png)",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default="config.yaml",
        help="Path to configuration file",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=None,
        help="Output width in pixels",
    )
    parser.add_argument(
        "--contrast",
        type=float,
        default=None,
        help="Contrast adjustment factor",
    )
    parser.add_argument(
        "--brightness",
        type=float,
        default=None,
        help="Brightness adjustment factor",
    )
    parser.add_argument(
        "--gamma",
        type=float,
        default=None,
        help="Gamma correction value",
    )
    parser.add_argument(
        "--no-bg-remove",
        action="store_true",
        default=False,
        help="Skip background removal",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


def load_image(path: str) -> np.ndarray:
    """Load an image from disk and return as an RGB numpy array."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path.resolve()}")
    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"Failed to decode image: {path}")
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def remove_background(img: np.ndarray) -> np.ndarray:
    """Remove background from image using rembg."""
    if not HAS_REMBG:
        logger.warning(
            "rembg not installed. Skipping background removal. "
            "Install with: pip install rembg onnxruntime"
        )
        return img
    logger.info("Removing background...")
    pil_img = Image.fromarray(img)
    result = remove_bg(pil_img)
    result_rgba = np.array(result)
    if result_rgba.shape[2] == 4:
        alpha = result_rgba[:, :, 3] / 255.0
        rgb = result_rgba[:, :, :3]
        white_bg = np.ones_like(rgb, dtype=np.uint8) * 255
        composite = (rgb * alpha[:, :, None] + white_bg * (1 - alpha[:, :, None])).astype(np.uint8)
        return composite
    return result_rgba[:, :, :3]


def resize_image(img: np.ndarray, target_width: int) -> np.ndarray:
    """Resize image to target width, maintaining aspect ratio."""
    h, w = img.shape[:2]
    aspect = h / w
    target_height = int(target_width * aspect)
    return cv2.resize(img, (target_width, target_height), interpolation=cv2.INTER_AREA)


def apply_clahe(img: np.ndarray, clip_limit: float = 2.0, grid_size: Tuple[int, int] = (8, 8)) -> np.ndarray:
    """Apply Contrast Limited Adaptive Histogram Equalisation."""
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=grid_size)
    enhanced = clahe.apply(gray)
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB)


def adjust_brightness_contrast(img: np.ndarray, brightness: float = 1.0, contrast: float = 1.0) -> np.ndarray:
    """Adjust brightness and contrast."""
    adjusted = img.astype(np.float32)
    adjusted = adjusted * contrast + (brightness - 1.0) * 128.0
    adjusted = np.clip(adjusted, 0, 255).astype(np.uint8)
    return adjusted


def apply_gamma(img: np.ndarray, gamma: float = 1.0) -> np.ndarray:
    """Apply gamma correction."""
    if gamma == 1.0:
        return img
    inv_gamma = 1.0 / gamma
    table = np.array([(i / 255.0) ** inv_gamma * 255 for i in range(256)]).astype(np.uint8)
    return cv2.LUT(img, table)


def to_grayscale(img: np.ndarray) -> np.ndarray:
    """Convert RGB to grayscale (single channel)."""
    return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)


def composite_on_bg(gray: np.ndarray, bg_color: int = 255) -> np.ndarray:
    """Ensure background pixels map to the specified grayscale value."""
    return gray.astype(np.uint8)


def process_photo(
    input_path: str,
    output_path: str,
    target_width: int = 800,
    contrast: float = 1.2,
    brightness: float = 1.0,
    gamma: float = 1.0,
    remove_bg_flag: bool = True,
) -> str:
    """
    Full photo processing pipeline.

    Returns the path to the processed image.
    """
    logger.info(f"Loading image: {input_path}")
    img = load_image(input_path)
    logger.info(f"Original size: {img.shape[1]}x{img.shape[0]}")

    if remove_bg_flag:
        img = remove_background(img)

    img = resize_image(img, target_width)
    logger.info(f"Resized to: {img.shape[1]}x{img.shape[0]}")

    img = apply_clahe(img)
    logger.info("CLAHE applied")

    img = adjust_brightness_contrast(img, brightness=brightness, contrast=contrast)
    logger.info(f"Brightness/contrast adjusted (b={brightness}, c={contrast})")

    img = apply_gamma(img, gamma=gamma)
    logger.info(f"Gamma applied (g={gamma})")

    gray = to_grayscale(img)
    logger.info("Converted to grayscale")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output), gray)
    logger.info(f"Saved processed image: {output.resolve()}")

    return str(output)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    setup_logging(level=logging.DEBUG if args.verbose else logging.INFO)

    config = load_config(args.config)

    ascii_cfg = config.get("ascii", {})
    photo_cfg = ascii_cfg.get("photo", {})

    input_path = args.input or ascii_cfg.get("source_image", "assets/profile-photo.jpg")
    output_path = args.output or "assets/source-prepped.png"
    target_width = args.width or photo_cfg.get("output_width", 800)
    contrast = args.contrast or photo_cfg.get("contrast", 1.2)
    brightness = args.brightness or photo_cfg.get("brightness", 1.0)
    gamma = args.gamma or photo_cfg.get("gamma", 1.0)
    remove_bg_flag = not args.no_bg_remove and photo_cfg.get("bg_remove", True)

    try:
        process_photo(
            input_path=input_path,
            output_path=output_path,
            target_width=target_width,
            contrast=contrast,
            brightness=brightness,
            gamma=gamma,
            remove_bg_flag=remove_bg_flag,
        )
        return 0
    except (FileNotFoundError, ValueError) as exc:
        logger.error(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
