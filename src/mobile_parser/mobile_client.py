# coding: utf-8
"""Mobile device client - direct control via mobilecli + WebDriverAgent + adb + xcrun simctl.

Supports both iOS and Android:
- iOS: mobilecli + WebDriverAgent + xcrun simctl
- Android: adb (Android Debug Bridge)
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

from .mobilecli import Mobilecli, DeviceInfo, get_mobilecli
from .wda import WebDriverAgent, WDAError, WDA_BUNDLE_ID

logger = logging.getLogger(__name__)


def _get_adb_path() -> str:
    """Find adb binary."""
    # Check ANDROID_HOME / ANDROID_SDK_ROOT
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        sdk = os.environ.get(env)
        if sdk:
            adb = os.path.join(sdk, "platform-tools", "adb")
            if os.path.isfile(adb):
                return adb
    # Fallback to PATH
    adb = shutil.which("adb")
    if adb:
        return adb
    raise MobileClientError("adb not found. Install Android SDK platform-tools.")


class MobileClientError(Exception):
    """Error from MobileClient operations."""
    pass


class MobileClient:
    """Direct mobile device control using mobilecli + WDA + xcrun simctl + adb."""

    def __init__(self) -> None:
        self._mobilecli: Mobilecli | None = None
        self._wda_instances: dict[str, WebDriverAgent] = {}
        self._wda_sessions: dict[str, str] = {}
        self._screen_sizes: dict[str, dict[str, int]] = {}
        self._device_platforms: dict[str, str] = {}  # device_id -> "ios" | "android"

    @property
    def mobilecli(self) -> Mobilecli:
        if self._mobilecli is None:
            self._mobilecli = get_mobilecli()
        return self._mobilecli

    def _detect_platform(self, device: str) -> str:
        """Detect if device is iOS or Android."""
        if device in self._device_platforms:
            return self._device_platforms[device]

        # Check adb devices
        try:
            adb = _get_adb_path()
            result = subprocess.run(
                [adb, "devices"], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.strip().split("\n")[1:]:
                parts = line.split("\t")
                if len(parts) >= 2 and parts[0] == device and parts[1] == "device":
                    self._device_platforms[device] = "android"
                    return "android"
        except (MobileClientError, subprocess.TimeoutExpired):
            pass

        # Check mobilecli devices
        try:
            devices = self.mobilecli.get_devices(include_offline=False)
            for d in devices:
                if d.id == device:
                    self._device_platforms[device] = d.platform
                    return d.platform
        except Exception:
            pass

        # Default to iOS for backward compatibility
        self._device_platforms[device] = "ios"
        return "ios"

    def _is_android(self, device: str) -> bool:
        return self._detect_platform(device) == "android"

    # ===== ADB helpers =====

    def _adb(self, device: str, args: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
        """Run adb command for a device."""
        adb = _get_adb_path()
        cmd = [adb, "-s", device] + args
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return result

    def _adb_text(self, device: str, args: list[str], timeout: int = 10) -> str:
        """Run adb command and return stdout as text."""
        result = self._adb(device, args, timeout)
        if result.returncode != 0:
            raise MobileClientError(
                f"adb {' '.join(args)} failed: {result.stderr.decode(errors='replace').strip()}"
            )
        return result.stdout.decode(errors="replace").strip()

    # ===== iOS helpers (unchanged) =====

    def _get_wda(self, device: str) -> WebDriverAgent:
        """Get or create WDA instance for a device."""
        if device not in self._wda_instances:
            self._wda_instances[device] = WebDriverAgent("localhost", 8100)
        return self._wda_instances[device]

    def _ensure_wda_running(self, device: str) -> WebDriverAgent:
        """Ensure WDA is running on the device, auto-starting if needed."""
        wda = self._get_wda(device)

        if wda.is_running():
            return wda

        logger.info(f"WDA not running on {device}, attempting auto-start...")
        self._start_wda_on_simulator(device)

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
            result = subprocess.run(
                ["xcrun", "simctl", "listapps", device],
                capture_output=True, text=True, timeout=10
            )
            if WDA_BUNDLE_ID not in result.stdout:
                logger.warning(f"WDA ({WDA_BUNDLE_ID}) not installed on {device}")
                return

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
            return "No devices found. Make sure a Simulator or Emulator is running."

        lines = []
        for d in devices:
            lines.append(f"{d.name} ({d.platform} {d.type}) - {d.id}")
        return "\n".join(lines)

    async def get_screen_size(self, device: str) -> str:
        """Get screen size of device."""
        loop = asyncio.get_running_loop()

        def _get():
            if self._is_android(device):
                return self._android_get_screen_size(device)
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
            if self._is_android(device):
                return self._android_get_screen_size(device)
            wda, session_id = self._get_session(device)
            size = wda.get_screen_size(session_id)
            self._screen_sizes[device] = size
            return size

        return await loop.run_in_executor(None, _get)

    def _android_get_screen_size(self, device: str) -> dict[str, int]:
        """Get Android screen size via adb."""
        output = self._adb_text(device, ["shell", "wm", "size"])
        # Output: "Physical size: 1080x2340" or "Override size: ..."
        match = re.search(r"(\d+)x(\d+)", output.split("\n")[-1])
        if not match:
            raise MobileClientError(f"Could not parse screen size: {output}")
        size = {"width": int(match.group(1)), "height": int(match.group(2))}
        self._screen_sizes[device] = size
        return size

    async def list_apps(self, device: str) -> str:
        """List installed apps on device."""
        loop = asyncio.get_running_loop()

        def _list():
            if self._is_android(device):
                output = self._adb_text(device, ["shell", "pm", "list", "packages", "-3"])
                packages = [line.replace("package:", "") for line in output.split("\n") if line.startswith("package:")]
                return "\n".join(sorted(packages))

            result = subprocess.run(
                ["xcrun", "simctl", "listapps", device],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                raise MobileClientError(f"Failed to list apps: {result.stderr}")

            convert = subprocess.run(
                ["plutil", "-convert", "json", "-o", "-", "-"],
                input=result.stdout, capture_output=True, text=True, timeout=10
            )
            if convert.returncode != 0:
                return result.stdout

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
            if self._is_android(device):
                # Use monkey to launch the app's default activity
                self._adb_text(device, [
                    "shell", "monkey", "-p", package_name,
                    "-c", "android.intent.category.LAUNCHER", "1"
                ])
                return f"Launched {package_name}"

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
            if self._is_android(device):
                self._adb_text(device, ["shell", "am", "force-stop", package_name])
                return f"Terminated {package_name}"

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
            if self._is_android(device):
                self._adb_text(device, [
                    "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url
                ])
                return f"Opened {url}"

            wda, session_id = self._get_session(device)
            wda.open_url(session_id, url)
            return f"Opened {url}"

        return await loop.run_in_executor(None, _open)

    # ===== Interactions =====

    async def tap(self, device: str, x: float, y: float) -> str:
        """Tap at coordinates."""
        loop = asyncio.get_running_loop()

        def _tap():
            if self._is_android(device):
                self._adb_text(device, ["shell", "input", "tap", str(int(x)), str(int(y))])
                return f"Tapped ({x}, {y})"

            wda, session_id = self._get_session(device)
            wda.tap(session_id, x, y)
            return f"Tapped ({x}, {y})"

        return await loop.run_in_executor(None, _tap)

    async def double_tap(self, device: str, x: float, y: float) -> str:
        """Double-tap at coordinates."""
        loop = asyncio.get_running_loop()

        def _double_tap():
            if self._is_android(device):
                self._adb_text(device, ["shell", "input", "tap", str(int(x)), str(int(y))])
                time.sleep(0.05)
                self._adb_text(device, ["shell", "input", "tap", str(int(x)), str(int(y))])
                return f"Double-tapped ({x}, {y})"

            wda, session_id = self._get_session(device)
            wda.double_tap(session_id, x, y)
            return f"Double-tapped ({x}, {y})"

        return await loop.run_in_executor(None, _double_tap)

    async def long_press(self, device: str, x: float, y: float, duration: float = 500) -> str:
        """Long press at coordinates."""
        loop = asyncio.get_running_loop()

        def _long_press():
            if self._is_android(device):
                # adb swipe with same start/end = long press
                self._adb_text(device, [
                    "shell", "input", "swipe",
                    str(int(x)), str(int(y)), str(int(x)), str(int(y)), str(int(duration))
                ])
                return f"Long-pressed ({x}, {y}) for {duration}ms"

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
            size = self._screen_sizes.get(device)
            if not size:
                if self._is_android(device):
                    size = self._android_get_screen_size(device)
                else:
                    wda, session_id = self._get_session(device)
                    size = wda.get_screen_size(session_id)
                    self._screen_sizes[device] = size

            sw, sh = size["width"], size["height"]
            start_x = x if x is not None else sw / 2
            start_y = y if y is not None else sh / 2

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

            if self._is_android(device):
                self._adb_text(device, [
                    "shell", "input", "swipe",
                    str(int(start_x)), str(int(start_y)),
                    str(int(end_x)), str(int(end_y)), "300"
                ])
                return f"Swiped {direction}"

            wda, session_id = self._get_session(device)
            wda.swipe(session_id, start_x, start_y, end_x, end_y)
            return f"Swiped {direction}"

        return await loop.run_in_executor(None, _swipe)

    async def type_text(self, device: str, text: str, submit: bool = False) -> str:
        """Type text."""
        loop = asyncio.get_running_loop()

        def _type():
            if self._is_android(device):
                # Escape special characters for adb shell input text
                escaped = text.replace("\\", "\\\\").replace(" ", "%s").replace("&", "\\&").replace("<", "\\<").replace(">", "\\>").replace("'", "\\'").replace('"', '\\"').replace("(", "\\(").replace(")", "\\)").replace("|", "\\|").replace(";", "\\;").replace("@", "\\@")
                self._adb_text(device, ["shell", "input", "text", escaped])
                if submit:
                    self._adb_text(device, ["shell", "input", "keyevent", "66"])  # KEYCODE_ENTER
                return f"Typed: {text}"

            wda, session_id = self._get_session(device)
            full_text = text + "\n" if submit else text
            wda.send_keys(session_id, full_text)
            return f"Typed: {text}"

        return await loop.run_in_executor(None, _type)

    async def press_button(self, device: str, button: str) -> str:
        """Press hardware button."""
        loop = asyncio.get_running_loop()

        def _press():
            if self._is_android(device):
                # Map common button names to Android keycodes
                keycode_map = {
                    "HOME": "3",
                    "BACK": "4",
                    "VOLUME_UP": "24",
                    "VOLUME_DOWN": "25",
                    "POWER": "26",
                    "ENTER": "66",
                    "DELETE": "67",
                    "MENU": "82",
                    "TAB": "61",
                }
                keycode = keycode_map.get(button.upper(), button)
                self._adb_text(device, ["shell", "input", "keyevent", keycode])
                return f"Pressed {button}"

            wda, session_id = self._get_session(device)
            wda.press_button(session_id, button)
            return f"Pressed {button}"

        return await loop.run_in_executor(None, _press)

    # ===== Screenshots =====

    async def take_screenshot(self, device: str) -> bytes:
        """Take screenshot, return PNG bytes."""
        loop = asyncio.get_running_loop()

        def _screenshot():
            if self._is_android(device):
                result = self._adb(device, ["exec-out", "screencap", "-p"], timeout=10)
                if result.returncode != 0:
                    raise MobileClientError(
                        f"Screenshot failed: {result.stderr.decode(errors='replace').strip()}"
                    )
                return result.stdout

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
