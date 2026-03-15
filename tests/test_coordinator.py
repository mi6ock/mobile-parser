# coding: utf-8
"""Tests for the Coordinator class."""

import base64

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mobile_parser.coordinator import Coordinator


# ---------------------------------------------------------------------------
# Coordinator.find_elements — coordinate conversion
# ---------------------------------------------------------------------------


async def test_find_elements_coordinate_conversion(mock_mobile):
    """Verify image-pixel -> logical-pixel coordinate conversion."""
    # Image: 1290x2796, Screen: 430x932
    # Element center: (645, 1398) -> tap: (215, 466)
    fake_parsed = {
        "image_size": {"width": 1290, "height": 2796},
        "elements": [
            {
                "id": 0,
                "type": "text",
                "content": "Hello",
                "center_x": 645,
                "center_y": 1398,
                "bbox": [0.4, 0.4, 0.6, 0.6],
            },
        ],
        "annotated_image": base64.b64encode(b"fake_png").decode(),
    }

    mock_parser = MagicMock()
    mock_parser.parse_image.return_value = fake_parsed

    mock_mobile.save_screenshot = AsyncMock(return_value="Saved")
    mock_mobile.get_screen_size_dict = AsyncMock(
        return_value={"width": 430, "height": 932, "scale": 3}
    )

    coord = Coordinator(mock_mobile)

    with patch("mobile_parser.coordinator._get_parser", return_value=mock_parser):
        result = await coord.find_elements("dev1", box_threshold=0.05)

    elem = result["elements"][0]
    assert elem["tap_x"] == 215
    assert elem["tap_y"] == 466
    assert result["screen_size"] == {"width": 430, "height": 932}
    assert result["image_size"] == {"width": 1290, "height": 2796}


async def test_find_elements_pipeline_calls(mock_mobile):
    """Verify the full pipeline: save_screenshot -> get_screen_size -> parse_image."""
    fake_parsed = {
        "image_size": {"width": 1000, "height": 2000},
        "elements": [],
        "annotated_image": base64.b64encode(b"img").decode(),
    }

    mock_parser = MagicMock()
    mock_parser.parse_image.return_value = fake_parsed

    mock_mobile.save_screenshot = AsyncMock(return_value="Saved")
    mock_mobile.get_screen_size_dict = AsyncMock(
        return_value={"width": 500, "height": 1000, "scale": 2}
    )

    coord = Coordinator(mock_mobile)

    with patch("mobile_parser.coordinator._get_parser", return_value=mock_parser):
        await coord.find_elements("dev1")

    mock_mobile.save_screenshot.assert_called_once()
    mock_mobile.get_screen_size_dict.assert_called_once_with("dev1")
    mock_parser.parse_image.assert_called_once()


# ---------------------------------------------------------------------------
# Coordinator.parse_image_file
# ---------------------------------------------------------------------------


async def test_parse_image_file(mock_mobile):
    """parse_image_file passes through to OmniParser without coordinate conversion."""
    fake_parsed = {
        "image_size": {"width": 800, "height": 600},
        "elements": [
            {
                "id": 0,
                "type": "icon",
                "content": "menu",
                "center_x": 400,
                "center_y": 300,
                "bbox": [0.4, 0.4, 0.6, 0.6],
            },
        ],
        "annotated_image": base64.b64encode(b"annotated").decode(),
    }

    mock_parser = MagicMock()
    mock_parser.parse_image.return_value = fake_parsed

    coord = Coordinator(mock_mobile)

    with patch("mobile_parser.coordinator._get_parser", return_value=mock_parser):
        result = await coord.parse_image_file("/tmp/screenshot.png", 0.1)

    mock_parser.parse_image.assert_called_once_with("/tmp/screenshot.png", 0.1)
    assert result == fake_parsed
    # No tap_x/tap_y should be added
    assert "tap_x" not in result["elements"][0]


# ---------------------------------------------------------------------------
# Coordinate precision test (important for WebView apps like sample_app)
# ---------------------------------------------------------------------------


async def test_coordinate_conversion_precision(mock_mobile):
    """Test that coordinate conversion is precise for various screen/image ratios.

    This is critical for apps like sample_app (Flutter WebView) where standard
    accessibility-based coordinate estimation fails.
    """
    # Test multiple device configurations
    test_cases = [
        # (img_w, img_h, screen_w, screen_h, center_x, center_y, expected_tap_x, expected_tap_y)
        (1290, 2796, 430, 932, 645, 1398, 215, 466),    # iPhone 16 Pro (3x)
        (1179, 2556, 393, 852, 590, 1278, 197, 426),    # iPhone 15 (3x)
        (1284, 2778, 428, 926, 642, 1389, 214, 463),    # iPhone 14 Pro (3x)
        (750, 1334, 375, 667, 375, 667, 188, 334),      # iPhone SE (2x)
    ]

    for img_w, img_h, screen_w, screen_h, cx, cy, exp_tx, exp_ty in test_cases:
        fake_parsed = {
            "image_size": {"width": img_w, "height": img_h},
            "elements": [{
                "id": 0, "type": "text", "content": "test",
                "center_x": cx, "center_y": cy,
                "bbox": [0.4, 0.4, 0.6, 0.6],
            }],
            "annotated_image": base64.b64encode(b"img").decode(),
        }

        mock_parser = MagicMock()
        mock_parser.parse_image.return_value = fake_parsed

        mock_mobile.save_screenshot = AsyncMock(return_value="Saved")
        mock_mobile.get_screen_size_dict = AsyncMock(
            return_value={"width": screen_w, "height": screen_h, "scale": img_w // screen_w}
        )

        coord = Coordinator(mock_mobile)

        with patch("mobile_parser.coordinator._get_parser", return_value=mock_parser):
            result = await coord.find_elements("dev1")

        elem = result["elements"][0]
        assert elem["tap_x"] == exp_tx, f"tap_x mismatch for {screen_w}x{screen_h}: {elem['tap_x']} != {exp_tx}"
        assert elem["tap_y"] == exp_ty, f"tap_y mismatch for {screen_w}x{screen_h}: {elem['tap_y']} != {exp_ty}"
