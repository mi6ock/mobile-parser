# coding: utf-8
"""Mobile Parser MCP Server - Mobile testing with OmniParser UI detection + device control."""

import os
import base64
from typing import Any

from mcp.server.fastmcp import FastMCP, Image as MCPImage

from .mobile_client import MobileClient
from .coordinator import Coordinator

# Set MPS fallback for macOS
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

# Create MCP server
mcp = FastMCP("mobile-parser")

# Shared instances (initialized on first tool call)
_mobile: MobileClient | None = None
_coordinator: Coordinator | None = None


async def _get_mobile() -> MobileClient:
    """Get or create the mobile-mcp client."""
    global _mobile
    if _mobile is None:
        _mobile = MobileClient()
        await _mobile.start()
    return _mobile


async def _get_coordinator() -> Coordinator:
    """Get or create the coordinator."""
    global _coordinator
    if _coordinator is None:
        mobile = await _get_mobile()
        _coordinator = Coordinator(mobile)
    return _coordinator


async def _proxy(tool_name: str, arguments: dict[str, Any]) -> str:
    """Proxy a tool call to mobile-mcp and return its text output."""
    mobile = await _get_mobile()
    result = await mobile.call_tool(tool_name, arguments)
    return _extract_text(result)


async def _proxy_with_image(tool_name: str, arguments: dict[str, Any]) -> list:
    """Proxy a tool call to mobile-mcp and return text + image output."""
    mobile = await _get_mobile()
    result = await mobile.call_tool(tool_name, arguments)
    return _extract_all_content(result)


def _extract_text(result: Any) -> str:
    """Extract text content from an MCP call_tool result."""
    if hasattr(result, "content"):
        texts = []
        for item in result.content:
            if hasattr(item, "text"):
                texts.append(item.text)
        if texts:
            return "\n".join(texts)
    return str(result)


def _extract_all_content(result: Any) -> list:
    """Extract all content (text + images) from an MCP call_tool result."""
    items = []
    if hasattr(result, "content"):
        for item in result.content:
            if hasattr(item, "text"):
                items.append(item.text)
            elif hasattr(item, "data") and hasattr(item, "mimeType"):
                # Image content - convert to MCPImage
                data = item.data
                if isinstance(data, str):
                    data = base64.b64decode(data)
                fmt = "png" if "png" in (item.mimeType or "") else "jpeg"
                items.append(MCPImage(data=data, format=fmt))
    return items if items else [str(result)]


# ===========================================================================
# Device management tools (proxied from mobile-mcp)
# ===========================================================================


@mcp.tool()
async def mobile_list_devices() -> str:
    """List all available devices (physical devices and simulators)."""
    return await _proxy("mobile_list_available_devices", {"noParams": {}})


@mcp.tool()
async def mobile_get_screen_size(device: str) -> str:
    """Get the screen size of the mobile device in pixels.

    Args:
        device: Device identifier (from mobile_list_devices)
    """
    return await _proxy("mobile_get_screen_size", {"device": device})


@mcp.tool()
async def mobile_list_apps(device: str) -> str:
    """List all installed apps on the device.

    Args:
        device: Device identifier
    """
    return await _proxy("mobile_list_apps", {"device": device})


@mcp.tool()
async def mobile_launch_app(device: str, packageName: str) -> str:
    """Launch an app on the mobile device.

    Args:
        device: Device identifier
        packageName: Package name of the app to launch
    """
    return await _proxy(
        "mobile_launch_app", {"device": device, "packageName": packageName}
    )


@mcp.tool()
async def mobile_terminate_app(device: str, packageName: str) -> str:
    """Stop and terminate an app on the mobile device.

    Args:
        device: Device identifier
        packageName: Package name of the app to terminate
    """
    return await _proxy(
        "mobile_terminate_app", {"device": device, "packageName": packageName}
    )


@mcp.tool()
async def mobile_open_url(device: str, url: str) -> str:
    """Open a URL in the browser on the device.

    Args:
        device: Device identifier
        url: The URL to open
    """
    return await _proxy("mobile_open_url", {"device": device, "url": url})


# ===========================================================================
# Interaction tools (proxied from mobile-mcp)
# ===========================================================================


@mcp.tool()
async def mobile_tap(device: str, x: float, y: float) -> str:
    """Tap on the screen at given coordinates.

    Args:
        device: Device identifier
        x: X coordinate in logical pixels
        y: Y coordinate in logical pixels
    """
    return await _proxy(
        "mobile_click_on_screen_at_coordinates",
        {"device": device, "x": x, "y": y},
    )


@mcp.tool()
async def mobile_double_tap(device: str, x: float, y: float) -> str:
    """Double-tap on the screen at given coordinates.

    Args:
        device: Device identifier
        x: X coordinate in logical pixels
        y: Y coordinate in logical pixels
    """
    return await _proxy(
        "mobile_double_tap_on_screen",
        {"device": device, "x": x, "y": y},
    )


@mcp.tool()
async def mobile_long_press(
    device: str, x: float, y: float, duration: float | None = None
) -> str:
    """Long press on the screen at given coordinates.

    Args:
        device: Device identifier
        x: X coordinate in logical pixels
        y: Y coordinate in logical pixels
        duration: Duration in milliseconds (default 500ms)
    """
    args: dict[str, Any] = {"device": device, "x": x, "y": y}
    if duration is not None:
        args["duration"] = duration
    return await _proxy("mobile_long_press_on_screen_at_coordinates", args)


@mcp.tool()
async def mobile_swipe(
    device: str,
    direction: str,
    x: float | None = None,
    y: float | None = None,
    distance: float | None = None,
) -> str:
    """Swipe on the screen.

    Args:
        device: Device identifier
        direction: Swipe direction (up, down, left, right)
        x: Starting X coordinate (default: center)
        y: Starting Y coordinate (default: center)
        distance: Swipe distance in pixels
    """
    args: dict[str, Any] = {"device": device, "direction": direction}
    if x is not None:
        args["x"] = x
    if y is not None:
        args["y"] = y
    if distance is not None:
        args["distance"] = distance
    return await _proxy("mobile_swipe_on_screen", args)


@mcp.tool()
async def mobile_type_text(device: str, text: str, submit: bool = False) -> str:
    """Type text into the focused element.

    Args:
        device: Device identifier
        text: The text to type
        submit: Whether to press enter after typing
    """
    return await _proxy(
        "mobile_type_keys", {"device": device, "text": text, "submit": submit}
    )


@mcp.tool()
async def mobile_press_button(device: str, button: str) -> str:
    """Press a hardware button on the device.

    Args:
        device: Device identifier
        button: Button name (HOME, BACK, VOLUME_UP, VOLUME_DOWN, ENTER, etc.)
    """
    return await _proxy(
        "mobile_press_button", {"device": device, "button": button}
    )


# ===========================================================================
# Screen analysis tools (OmniParser local execution)
# ===========================================================================


@mcp.tool()
async def mobile_screenshot(device: str) -> list:
    """Take a screenshot of the mobile device (returns base64 image).

    Args:
        device: Device identifier
    """
    return await _proxy_with_image("mobile_take_screenshot", {"device": device})


@mcp.tool()
async def mobile_save_screenshot(device: str, saveTo: str) -> str:
    """Save a screenshot of the mobile device to a file.

    Args:
        device: Device identifier
        saveTo: File path to save the screenshot
    """
    return await _proxy(
        "mobile_save_screenshot", {"device": device, "saveTo": saveTo}
    )


@mcp.tool()
async def mobile_find_elements(
    device: str, box_threshold: float = 0.05
) -> list:
    """Take a screenshot, detect UI elements with OmniParser, and return
    coordinate-converted results ready for tapping.

    This is the primary tool for interacting with mobile UI. It:
    1. Takes a screenshot of the device
    2. Runs OmniParser to detect all UI elements
    3. Converts pixel coordinates to logical screen coordinates

    The returned tap_x/tap_y can be passed directly to mobile_tap().

    Args:
        device: Device identifier
        box_threshold: Detection confidence threshold (0.0-1.0, default 0.05)

    Returns:
        List containing:
        - Text with detected elements and their tap coordinates
        - Annotated image with bounding boxes and IDs
    """
    coordinator = await _get_coordinator()
    result = await coordinator.find_elements(device, box_threshold)

    # Format output
    text = _format_find_elements(result)

    # Annotated image
    items: list[Any] = [text]
    if result.get("annotated_image"):
        image_bytes = base64.b64decode(result["annotated_image"])
        items.append(MCPImage(data=image_bytes, format="png"))

    return items


@mcp.tool()
async def mobile_parse_image(
    image_path: str, box_threshold: float = 0.05
) -> list:
    """Parse an existing image file and extract UI elements with coordinates.

    Use this for analyzing previously saved screenshots. For live device
    interaction, prefer mobile_find_elements which handles the full pipeline.

    Args:
        image_path: Path to the image file to parse
        box_threshold: Detection confidence threshold (0.0-1.0, default 0.05)

    Returns:
        List containing:
        - Text description of detected elements with coordinates
        - Annotated image with bounding boxes and IDs
    """
    coordinator = await _get_coordinator()
    result = await coordinator.parse_image_file(image_path, box_threshold)

    # Format output (same as omniparser-simple)
    elements_text = _format_elements_raw(result["elements"], result["image_size"])
    image_bytes = base64.b64decode(result["annotated_image"])

    return [elements_text, MCPImage(data=image_bytes, format="png")]


# ===========================================================================
# Formatting helpers
# ===========================================================================


def _format_find_elements(result: dict) -> str:
    """Format find_elements output with tap coordinates."""
    screen = result["screen_size"]
    img = result["image_size"]
    elems = result["elements"]

    lines = [
        f"Device screen: {screen['width']}x{screen['height']} logical pixels",
        f"Image: {img['width']}x{img['height']} pixels",
        "",
        f"Found {len(elems)} elements:",
        "",
    ]

    for elem in elems:
        content_label = elem["type"]  # "text" or "icon"
        lines.append(
            f"ID: {elem['id']}, {content_label}: \"{elem['content']}\", "
            f"tap: ({elem['tap_x']}, {elem['tap_y']})"
        )

    return "\n".join(lines)


def _format_elements_raw(elements: list, image_size: dict) -> str:
    """Format elements list as readable text (without tap coordinate conversion)."""
    lines = [f"Image size: {image_size['width']}x{image_size['height']}", ""]
    lines.append(f"Found {len(elements)} elements:")
    lines.append("")

    for elem in elements:
        bbox = elem["bbox"]
        bbox_str = f"[{bbox[0]:.3f}, {bbox[1]:.3f}, {bbox[2]:.3f}, {bbox[3]:.3f}]"
        center_str = f"({elem['center_x']}, {elem['center_y']})"

        lines.append(
            f"ID: {elem['id']}, {elem['type']}: \"{elem['content']}\", "
            f"bbox: {bbox_str}, center: {center_str}"
        )

    return "\n".join(lines)


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
