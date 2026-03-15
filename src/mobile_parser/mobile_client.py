# coding: utf-8
"""Mobile device client - direct control via mobilecli + WebDriverAgent + xcrun simctl.

No dependency on mobile-mcp server. Directly uses:
- mobilecli binary for device discovery
- xcrun simctl for iOS simulator app management
- WebDriverAgent HTTP API for screen interactions
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from typing import Any

from .mobilecli import Mobilecli, DeviceInfo, get_mobilecli
from .wda import WebDriverAgent, WDAError, WDA_BUNDLE_ID

logger = logging.getLogger(__name__)


class MobileClientError(Exception):
    """Error from MobileClient operations."""
    pass


class MobileClient:
    """Direct mobile device control using mobilecli + WDA + xcrun simctl."""

    def __init__(self) -> None:
        self._mobilecli: Mobilecli | None = None
        self._wda_instances: dict[str, WebDriverAgent] = {}
        self._wda_sessions: dict[str, str] = {}
        self._screen_sizes: dict[str, dict[str, int]] = {}

    @property
    def mobilecli(self) -> Mobilecli:
        if self._mobilecli is None:
            self._mobilecli = get_mobilecli()
        return self._mobilecli

    def _get_wda(self, device: str) -> WebDriverAgent:
        """Get or create WDA instance for a device."""
        if device not in self._wda_instances:
            # iOS simulator: WDA runs on localhost:8100
            self._wda_instances[device] = WebDriverAgent("localhost", 8100)
        return self._wda_instances[device]

    def _ensure_wda_running(self, device: str) -> WebDriverAgent:
        """Ensure WDA is running on the device, auto-starting if needed."""
        wda = self._get_wda(device)

        if wda.is_running():
            return wda

        # Try to auto-start WDA on iOS simulator
        logger.info(f"WDA not running on {device}, attempting auto-start...")
        self._start_wda_on_simulator(device)

        # Poll for up to 10 seconds
        for _ in range(100):
            if wda.is_running():
                logger.info("WDA started successfully")
                return wda
            time.sleep(0.1)

        raise MobileClientError(
            f"WebDriverAgent is not running on device {device}. "
            f"Please install and launch WebDriverAgent on your simulator.\n"
            f"See: https://github.com/nicholasyan/mobile-mcp/wiki/Setup-for-iOS-Simulator"
        )

    def _start_wda_on_simulator(self, device: str) -> None:
        """Try to launch WDA on an iOS simulator via xcrun simctl."""
        try:
            # Check if WDA is installed
            result = subprocess.run(
                ["xcrun", "simctl", "listapps", device],
                capture_output=True, text=True, timeout=10
            )
            if WDA_BUNDLE_ID not in result.stdout:
                logger.warning(f"WDA ({WDA_BUNDLE_ID}) not installed on {device}")
                return

            # Launch WDA
            subprocess.run(
                ["xcrun", "simctl", "launch", device, WDA_BUNDLE_ID],
                capture_output=True, text=True, timeout=10
            )
            logger.info(f"Launched WDA on simulator {device}")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"Failed to auto-start WDA: {e}")

    def _get_session(self, device: str) -> tuple[WebDriverAgent, str]:
        """Get WDA instance and session ID, creating session if needed."""
        wda = self._ensure_wda_running(device)
        if device not in self._wda_sessions:
            self._wda_sessions[device] = wda.create_session()
        return wda, self._wda_sessions[device]

    # ===== Device Management =====

    async def list_devices(self) -> str:
        """List all available devices."""
        loop = asyncio.get_running_loop()
        devices = await loop.run_in_executor(
            None,
            lambda: self.mobilecli.get_devices(include_offline=False)
        )
        if not devices:
            return "No devices found. Make sure an iOS Simulator is booted."

        lines = []
        for d in devices:
            lines.append(f"{d.name} ({d.platform} {d.type}) - {d.id}")
        return "\n".join(lines)

    async def get_screen_size(self, device: str) -> str:
        """Get screen size of device."""
        loop = asyncio.get_running_loop()

        def _get():
            wda, session_id = self._get_session(device)
            size = wda.get_screen_size(session_id)
            self._screen_sizes[device] = size
            return size

        size = await loop.run_in_executor(None, _get)
        return f"{size['width']}x{size['height']}"

    async def get_screen_size_dict(self, device: str) -> dict[str, int]:
        """Get screen size as dict (for coordinator use)."""
        loop = asyncio.get_running_loop()

        def _get():
            if device in self._screen_sizes:
                return self._screen_sizes[device]
            wda, session_id = self._get_session(device)
            size = wda.get_screen_size(session_id)
            self._screen_sizes[device] = size
            return size

        return await loop.run_in_executor(None, _get)

    async def list_apps(self, device: str) -> str:
        """List installed apps on device."""
        loop = asyncio.get_running_loop()

        def _list():
            result = subprocess.run(
                ["xcrun", "simctl", "listapps", device],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                raise MobileClientError(f"Failed to list apps: {result.stderr}")

            # Convert plist to JSON
            convert = subprocess.run(
                ["plutil", "-convert", "json", "-o", "-", "-"],
                input=result.stdout, capture_output=True, text=True, timeout=10
            )
            if convert.returncode != 0:
                return result.stdout  # Fallback to raw plist

            apps = json.loads(convert.stdout)
            lines = []
            for bundle_id, info in apps.items():
                name = info.get("CFBundleDisplayName", info.get("CFBundleName", bundle_id))
                lines.append(f"{name}: {bundle_id}")
            return "\n".join(sorted(lines))

        return await loop.run_in_executor(None, _list)

    async def launch_app(self, device: str, package_name: str) -> str:
        """Launch an app on device."""
        loop = asyncio.get_running_loop()

        def _launch():
            result = subprocess.run(
                ["xcrun", "simctl", "launch", device, package_name],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                raise MobileClientError(f"Failed to launch {package_name}: {result.stderr}")
            return f"Launched {package_name}"

        return await loop.run_in_executor(None, _launch)

    async def terminate_app(self, device: str, package_name: str) -> str:
        """Terminate an app on device."""
        loop = asyncio.get_running_loop()

        def _terminate():
            result = subprocess.run(
                ["xcrun", "simctl", "terminate", device, package_name],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                raise MobileClientError(f"Failed to terminate {package_name}: {result.stderr}")
            return f"Terminated {package_name}"

        return await loop.run_in_executor(None, _terminate)

    async def open_url(self, device: str, url: str) -> str:
        """Open URL on device."""
        loop = asyncio.get_running_loop()

        def _open():
            wda, session_id = self._get_session(device)
            wda.open_url(session_id, url)
            return f"Opened {url}"

        return await loop.run_in_executor(None, _open)

    # ===== Interactions =====

    async def tap(self, device: str, x: float, y: float) -> str:
        """Tap at coordinates."""
        loop = asyncio.get_running_loop()

        def _tap():
            wda, session_id = self._get_session(device)
            wda.tap(session_id, x, y)
            return f"Tapped ({x}, {y})"

        return await loop.run_in_executor(None, _tap)

    async def double_tap(self, device: str, x: float, y: float) -> str:
        """Double-tap at coordinates."""
        loop = asyncio.get_running_loop()

        def _double_tap():
            wda, session_id = self._get_session(device)
            wda.double_tap(session_id, x, y)
            return f"Double-tapped ({x}, {y})"

        return await loop.run_in_executor(None, _double_tap)

    async def long_press(self, device: str, x: float, y: float, duration: float = 500) -> str:
        """Long press at coordinates."""
        loop = asyncio.get_running_loop()

        def _long_press():
            wda, session_id = self._get_session(device)
            wda.long_press(session_id, x, y, int(duration))
            return f"Long-pressed ({x}, {y}) for {duration}ms"

        return await loop.run_in_executor(None, _long_press)

    async def swipe(
        self, device: str, direction: str,
        x: float | None = None, y: float | None = None,
        distance: float | None = None,
    ) -> str:
        """Swipe on screen."""
        loop = asyncio.get_running_loop()

        def _swipe():
            wda, session_id = self._get_session(device)
            size = self._screen_sizes.get(device)
            if not size:
                size = wda.get_screen_size(session_id)
                self._screen_sizes[device] = size

            sw, sh = size["width"], size["height"]

            # Default: center of screen
            start_x = x if x is not None else sw / 2
            start_y = y if y is not None else sh / 2

            # Calculate end point
            dist = distance if distance is not None else min(sw, sh) * 0.6
            offsets = {
                "up": (0, -dist),
                "down": (0, dist),
                "left": (-dist, 0),
                "right": (dist, 0),
            }
            dx, dy = offsets.get(direction.lower(), (0, 0))
            end_x = start_x + dx
            end_y = start_y + dy

            wda.swipe(session_id, start_x, start_y, end_x, end_y)
            return f"Swiped {direction}"

        return await loop.run_in_executor(None, _swipe)

    async def type_text(self, device: str, text: str, submit: bool = False) -> str:
        """Type text."""
        loop = asyncio.get_running_loop()

        def _type():
            wda, session_id = self._get_session(device)
            full_text = text + "\n" if submit else text
            wda.send_keys(session_id, full_text)
            return f"Typed: {text}"

        return await loop.run_in_executor(None, _type)

    async def press_button(self, device: str, button: str) -> str:
        """Press hardware button."""
        loop = asyncio.get_running_loop()

        def _press():
            wda, session_id = self._get_session(device)
            wda.press_button(session_id, button)
            return f"Pressed {button}"

        return await loop.run_in_executor(None, _press)

    # ===== Screenshots =====

    async def take_screenshot(self, device: str) -> bytes:
        """Take screenshot, return PNG bytes."""
        loop = asyncio.get_running_loop()

        def _screenshot():
            wda = self._ensure_wda_running(device)
            return wda.get_screenshot()

        return await loop.run_in_executor(None, _screenshot)

    async def save_screenshot(self, device: str, path: str) -> str:
        """Save screenshot to file."""
        png_bytes = await self.take_screenshot(device)
        loop = asyncio.get_running_loop()

        def _save():
            os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
            with open(path, "wb") as f:
                f.write(png_bytes)
            return f"Saved screenshot to {path}"

        return await loop.run_in_executor(None, _save)
