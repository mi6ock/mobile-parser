# coding: utf-8
"""Shared fixtures for mobile-parser tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_mobile():
    """Return a mock MobileClient with all async methods mocked."""
    client = MagicMock()
    client.list_devices = AsyncMock(return_value="iPhone 16 Pro (ios simulator) - ABC-123")
    client.get_screen_size = AsyncMock(return_value="430x932")
    client.get_screen_size_dict = AsyncMock(return_value={"width": 430, "height": 932, "scale": 3})
    client.list_apps = AsyncMock(return_value="Safari: com.apple.Safari")
    client.launch_app = AsyncMock(return_value="Launched com.app")
    client.terminate_app = AsyncMock(return_value="Terminated com.app")
    client.open_url = AsyncMock(return_value="Opened https://example.com")
    client.tap = AsyncMock(return_value="Tapped (100, 200)")
    client.double_tap = AsyncMock(return_value="Double-tapped (100, 200)")
    client.long_press = AsyncMock(return_value="Long-pressed (100, 200) for 500ms")
    client.swipe = AsyncMock(return_value="Swiped up")
    client.type_text = AsyncMock(return_value="Typed: hello")
    client.press_button = AsyncMock(return_value="Pressed HOME")
    client.take_screenshot = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n")
    client.save_screenshot = AsyncMock(return_value="Saved screenshot to /tmp/x.png")
    return client


@pytest.fixture(autouse=True)
def reset_server_globals():
    """Reset server.py globals before and after every test."""
    import mobile_parser.server as srv
    srv._mobile = None
    srv._coordinator = None
    yield
    srv._mobile = None
    srv._coordinator = None
