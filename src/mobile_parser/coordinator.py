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
        self._screen_sizes: dict[str, tuple[int, int]] = {}

    async def _get_screen_size(self, device: str) -> tuple[int, int]:
        """Get logical screen size for a device, with caching."""
        if device not in self._screen_sizes:
            result = await self._mobile.call_tool(
                "mobile_get_screen_size", {"device": device}
            )
            # result.content is a list of content items
            text = _extract_text(result)
            w, h = _parse_screen_size(text)
            self._screen_sizes[device] = (w, h)
        return self._screen_sizes[device]

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
        await self._mobile.call_tool(
            "mobile_save_screenshot",
            {"device": device, "saveTo": screenshot_path},
        )

        # 2. Get screen size (cached)
        screen_w, screen_h = await self._get_screen_size(device)

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


def _extract_text(result: Any) -> str:
    """Extract text content from an MCP call_tool result."""
    if hasattr(result, "content"):
        for item in result.content:
            if hasattr(item, "text"):
                return item.text
    return str(result)


def _parse_screen_size(text: str) -> tuple[int, int]:
    """Parse screen size from mobile_get_screen_size output.

    Expected format varies, but typically contains width and height as integers.
    Examples: "430x932", "Width: 430, Height: 932", or JSON-like output.
    """
    import re

    # Try "WxH" pattern
    m = re.search(r"(\d+)\s*[xX\u00d7]\s*(\d+)", text)
    if m:
        return int(m.group(1)), int(m.group(2))

    # Try extracting two numbers (width, height order)
    nums = re.findall(r"\d+", text)
    if len(nums) >= 2:
        return int(nums[0]), int(nums[1])

    raise ValueError(f"Could not parse screen size from: {text}")
