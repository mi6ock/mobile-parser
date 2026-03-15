# coding: utf-8
"""Tests for server.py formatting functions."""

import pytest

from mobile_parser.server import (
    _format_find_elements,
    _format_elements_raw,
)


# ---------------------------------------------------------------------------
# _format_find_elements
# ---------------------------------------------------------------------------


class TestFormatFindElements:
    def test_basic(self):
        result = {
            "screen_size": {"width": 430, "height": 932},
            "image_size": {"width": 1290, "height": 2796},
            "elements": [
                {
                    "id": 0,
                    "type": "text",
                    "content": "Hello",
                    "tap_x": 215,
                    "tap_y": 466,
                },
            ],
        }
        text = _format_find_elements(result)
        assert "430x932" in text
        assert "1290x2796" in text
        assert "Found 1 elements" in text
        assert 'ID: 0, text: "Hello", tap: (215, 466)' in text

    def test_empty_elements(self):
        result = {
            "screen_size": {"width": 430, "height": 932},
            "image_size": {"width": 1290, "height": 2796},
            "elements": [],
        }
        text = _format_find_elements(result)
        assert "Found 0 elements" in text


# ---------------------------------------------------------------------------
# _format_elements_raw
# ---------------------------------------------------------------------------


class TestFormatElementsRaw:
    def test_basic(self):
        elements = [
            {
                "id": 0,
                "type": "icon",
                "content": "back arrow",
                "bbox": [0.1, 0.2, 0.3, 0.4],
                "center_x": 100,
                "center_y": 200,
            },
        ]
        image_size = {"width": 500, "height": 1000}
        text = _format_elements_raw(elements, image_size)
        assert "500x1000" in text
        assert "Found 1 elements" in text
        assert 'ID: 0, icon: "back arrow"' in text
        assert "[0.100, 0.200, 0.300, 0.400]" in text
        assert "(100, 200)" in text
