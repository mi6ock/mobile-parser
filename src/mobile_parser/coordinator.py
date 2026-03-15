# coding: utf-8
"""Coordinator: screenshot -> OmniParser -> coordinate conversion pipeline."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from typing import Any

from .mobile_client import MobileClient

logger = logging.getLogger(__name__)


def _get_parser():
    """Lazy import of OmniParser to avoid heavy load at startup."""
    from .parser import get_parser
    return get_parser()


class Coordinator:
    """Orchestrates screenshot capture, OmniParser analysis, and coordinate conversion."""

    def __init__(self, mobile: MobileClient) -> None:
        self._mobile = mobile

    async def find_elements(
        self, device: str, box_threshold: float = 0.05
    ) -> dict[str, Any]:
        """Take screenshot, run OmniParser, and convert coordinates.

        Returns dict with:
            - elements: list of elements with tap_x/tap_y in logical coordinates
            - image_size: original image dimensions
            - screen_size: logical screen dimensions
            - annotated_image: base64 annotated PNG
            - screenshot_path: path to saved screenshot
        """
        # 1. Save screenshot to temp file
        screenshot_path = tempfile.mktemp(suffix=".png", prefix="mobile_parser_")
        await self._mobile.save_screenshot(device, screenshot_path)

        # 2. Get screen size (cached inside mobile client)
        size = await self._mobile.get_screen_size_dict(device)
        screen_w, screen_h = size["width"], size["height"]

        # 3. Run OmniParser (in thread pool to avoid blocking)
        loop = asyncio.get_running_loop()
        parser = _get_parser()
        parsed = await loop.run_in_executor(
            None, parser.parse_image, screenshot_path, box_threshold
        )

        # 4. Convert coordinates from image pixels to logical screen coordinates
        img_w = parsed["image_size"]["width"]
        img_h = parsed["image_size"]["height"]

        for elem in parsed["elements"]:
            elem["tap_x"] = round(elem["center_x"] * screen_w / img_w)
            elem["tap_y"] = round(elem["center_y"] * screen_h / img_h)

        return {
            "elements": parsed["elements"],
            "image_size": parsed["image_size"],
            "screen_size": {"width": screen_w, "height": screen_h},
            "annotated_image": parsed.get("annotated_image"),
            "screenshot_path": screenshot_path,
        }

    async def parse_image_file(
        self, image_path: str, box_threshold: float = 0.05
    ) -> dict[str, Any]:
        """Parse an existing image file with OmniParser (no coordinate conversion)."""
        loop = asyncio.get_running_loop()
        parser = _get_parser()
        return await loop.run_in_executor(
            None, parser.parse_image, image_path, box_threshold
        )
