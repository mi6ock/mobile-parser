# coding: utf-8
"""WebDriverAgent HTTP client - direct communication with WDA on iOS devices."""

from __future__ import annotations

import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

WDA_BUNDLE_ID = "com.facebook.WebDriverAgentRunner.xctrunner"


class WDAError(Exception):
    """Error communicating with WebDriverAgent."""
    pass


class WebDriverAgent:
    """HTTP client for WebDriverAgent running on iOS device/simulator."""

    def __init__(self, host: str = "localhost", port: int = 8100) -> None:
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"

    def _request(self, method: str, path: str, body: dict | None = None, timeout: int = 30) -> Any:
        """Make HTTP request to WDA."""
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = resp.read()
                if content:
                    return json.loads(content)
                return None
        except urllib.error.HTTPError as e:
            body_text = e.read().decode(errors="replace")
            raise WDAError(f"WDA {method} {path} returned {e.code}: {body_text}")
        except urllib.error.URLError as e:
            raise WDAError(f"WDA connection failed ({url}): {e.reason}")

    def is_running(self) -> bool:
        """Check if WDA is running and ready."""
        try:
            result = self._request("GET", "/status", timeout=5)
            return result and result.get("value", {}).get("ready", False)
        except (WDAError, Exception):
            return False

    def create_session(self) -> str:
        """Create a new WDA session, return session ID."""
        result = self._request("POST", "/session", {
            "capabilities": {
                "alwaysMatch": {"platformName": "iOS"}
            }
        })
        session_id = result.get("value", {}).get("sessionId") or result.get("sessionId")
        if not session_id:
            raise WDAError(f"Failed to create WDA session: {result}")
        return session_id

    def delete_session(self, session_id: str) -> None:
        """Delete a WDA session."""
        try:
            self._request("DELETE", f"/session/{session_id}")
        except WDAError:
            pass  # Best effort

    def get_screen_size(self, session_id: str) -> dict[str, int]:
        """Get screen size (width, height, scale)."""
        result = self._request("GET", f"/session/{session_id}/wda/screen")
        value = result.get("value", {})
        return {
            "width": int(value.get("width", 0) / value.get("scale", 1)),
            "height": int(value.get("height", 0) / value.get("scale", 1)),
            "scale": value.get("scale", 1),
        }

    def get_screenshot(self) -> bytes:
        """Get screenshot as PNG bytes (no session needed)."""
        result = self._request("GET", "/screenshot")
        import base64
        b64_data = result.get("value", "")
        return base64.b64decode(b64_data)

    def tap(self, session_id: str, x: float, y: float) -> None:
        """Tap at coordinates."""
        self._request("POST", f"/session/{session_id}/actions", {
            "actions": [{
                "type": "pointer",
                "id": "finger1",
                "parameters": {"pointerType": "touch"},
                "actions": [
                    {"type": "pointerMove", "duration": 0, "x": x, "y": y},
                    {"type": "pointerDown"},
                    {"type": "pause", "duration": 100},
                    {"type": "pointerUp"},
                ]
            }]
        })

    def double_tap(self, session_id: str, x: float, y: float) -> None:
        """Double-tap at coordinates."""
        self._request("POST", f"/session/{session_id}/actions", {
            "actions": [{
                "type": "pointer",
                "id": "finger1",
                "parameters": {"pointerType": "touch"},
                "actions": [
                    {"type": "pointerMove", "duration": 0, "x": x, "y": y},
                    {"type": "pointerDown"},
                    {"type": "pause", "duration": 100},
                    {"type": "pointerUp"},
                    {"type": "pause", "duration": 100},
                    {"type": "pointerDown"},
                    {"type": "pause", "duration": 100},
                    {"type": "pointerUp"},
                ]
            }]
        })

    def long_press(self, session_id: str, x: float, y: float, duration: int = 500) -> None:
        """Long press at coordinates."""
        self._request("POST", f"/session/{session_id}/actions", {
            "actions": [{
                "type": "pointer",
                "id": "finger1",
                "parameters": {"pointerType": "touch"},
                "actions": [
                    {"type": "pointerMove", "duration": 0, "x": x, "y": y},
                    {"type": "pointerDown"},
                    {"type": "pause", "duration": duration},
                    {"type": "pointerUp"},
                ]
            }]
        })

    def swipe(
        self,
        session_id: str,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        duration: int = 1000,
    ) -> None:
        """Swipe from start to end coordinates."""
        self._request("POST", f"/session/{session_id}/actions", {
            "actions": [{
                "type": "pointer",
                "id": "finger1",
                "parameters": {"pointerType": "touch"},
                "actions": [
                    {"type": "pointerMove", "duration": 0, "x": start_x, "y": start_y},
                    {"type": "pointerDown"},
                    {"type": "pointerMove", "duration": duration, "x": end_x, "y": end_y},
                    {"type": "pointerUp"},
                ]
            }]
        })
        # Clear actions
        try:
            self._request("DELETE", f"/session/{session_id}/actions")
        except WDAError:
            pass

    def send_keys(self, session_id: str, text: str) -> None:
        """Type text via keyboard."""
        self._request("POST", f"/session/{session_id}/wda/keys", {
            "value": list(text)
        })

    def press_button(self, session_id: str, button: str) -> None:
        """Press hardware button (HOME, VOLUME_UP, VOLUME_DOWN)."""
        self._request("POST", f"/session/{session_id}/wda/pressButton", {
            "name": button.lower()
        })

    def open_url(self, session_id: str, url: str) -> None:
        """Open a URL."""
        self._request("POST", f"/session/{session_id}/url", {"url": url})

    def get_orientation(self, session_id: str) -> str:
        """Get screen orientation."""
        result = self._request("GET", f"/session/{session_id}/orientation")
        return result.get("value", "PORTRAIT").lower()

    def set_orientation(self, session_id: str, orientation: str) -> None:
        """Set screen orientation."""
        self._request("POST", f"/session/{session_id}/orientation", {
            "orientation": orientation.upper()
        })

    def get_source(self) -> dict:
        """Get page source tree (no session needed)."""
        return self._request("GET", "/source/?format=json")
