# coding: utf-8
"""Shared fixtures for mobile-parser tests."""

import base64
import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image as PILImage


def _make_test_png(width=100, height=200) -> bytes:
    """Create a small valid PNG for testing."""
    img = PILImage.new("RGB", (width, height), "red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


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
    client.take_screenshot = AsyncMock(return_value=_make_test_png())
    client.save_screenshot = AsyncMock(return_value="Saved screenshot to /tmp/x.png")
    return client


@pytest.fixture
def mock_coordinator():
    """Return a mock Coordinator that returns pre-built elements."""
    coord = MagicMock()
    coord.find_elements = AsyncMock(return_value={
        "elements": [
            {
                "id": 0,
                "type": "text",
                "content": "Hello",
                "tap_x": 215,
                "tap_y": 466,
                "center_x": 645,
                "center_y": 1398,
                "bbox": [0.4, 0.4, 0.6, 0.6],
            },
        ],
        "image_size": {"width": 1290, "height": 2796},
        "screen_size": {"width": 430, "height": 932},
        "annotated_image": base64.b64encode(_make_test_png()).decode(),
        "screenshot_path": "/tmp/screenshot.png",
    })
    return coord


@pytest.fixture(autouse=True)
def reset_server_globals():
    """Reset server.py globals before and after every test."""
    import mobile_parser.server as srv
    srv._mobile = None
    srv._coordinator = None
    srv._element_registry.clear()
    yield
    srv._mobile = None
    srv._coordinator = None
    srv._element_registry.clear()
