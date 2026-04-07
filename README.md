# mobile-parser

[![PyPI version](https://img.shields.io/pypi/v/mobile-parser?style=flat-square)](https://pypi.org/project/mobile-parser/)
[![Python](https://img.shields.io/pypi/pyversions/mobile-parser?style=flat-square)](https://pypi.org/project/mobile-parser/)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue?style=flat-square)](LICENSE)

An MCP server for mobile app testing that combines [OmniParser](https://github.com/microsoft/OmniParser) vision-based UI element detection with direct device control.

Unlike accessibility-tree-based tools, OmniParser detects UI elements directly from screenshots — making it work reliably with **Flutter, WebView, games, and any app** regardless of the UI framework.

## Features

- **Vision-based element detection** — OmniParser (YOLO + Florence-2 + EasyOCR) finds UI elements from screenshots
- **Cross-platform** — iOS Simulator and Android (emulator + real device)
- **Element ID-based interaction** — `find_elements` returns elements with IDs; pass the ID to `tap()`, `double_tap()`, `long_press()`
- **No Appium required** — talks directly to WDA (iOS) and adb (Android)
- **Auto-download everything** — models, tools, and dependencies fetched on first use

## Installation

### Claude Code

```bash
claude mcp add mobile-parser -- uvx mobile-parser
```

<details>
<summary>Claude Desktop / Cursor / Other MCP Clients</summary>

Add to your MCP config JSON:

```json
{
  "mcpServers": {
    "mobile-parser": {
      "command": "uvx",
      "args": ["mobile-parser"]
    }
  }
}
```

</details>

### Prerequisites

- **Python 3.10+** (managed by uv automatically)
- **Node.js / npm** (for mobilecli — auto-downloaded via npx)

<details>
<summary>iOS</summary>

- **Xcode + iOS Simulator**
- **WebDriverAgent** installed on the simulator
  - See: [Setup for iOS Simulator](https://github.com/nicholasyan/mobile-mcp/wiki/Setup-for-iOS-Simulator)

</details>

<details>
<summary>Android</summary>

- **Android SDK** (`adb` in PATH or `ANDROID_HOME` set)
- **Emulator or device** connected via `adb`

</details>

### What gets auto-downloaded

| Component | When | Size |
|-----------|------|------|
| Python packages (torch, etc.) | First `uvx mobile-parser` run | ~2 GB |
| mobilecli binary | First device operation | ~20 MB |
| OmniParser models | First `mobile_find_elements` call | ~1.5 GB |
| Florence-2 processor | First icon captioning | ~500 MB |

## Usage

```
1. mobile_find_elements(device="...") → elements with IDs and coordinates
2. mobile_tap(device="...", element_id=0) → tap the element by ID
```

`mobile_find_elements` handles the full pipeline:

1. Takes a screenshot of the device
2. Runs OmniParser to detect all UI elements (text + icons)
3. Converts pixel coordinates to logical screen coordinates
4. Registers elements by ID for subsequent tap/double_tap/long_press

You **must** call `mobile_find_elements` before tapping — `mobile_tap`, `mobile_double_tap`, and `mobile_long_press` require an element ID, not raw coordinates.

### Example prompts

- *"Find and tap the Login button"*
- *"Scroll down and look for a search bar"*
- *"Launch the Settings app and navigate to Wi-Fi"*
- *"Take a screenshot and describe what's on screen"*

## Tools

<details open>
<summary><strong>Screen Analysis (OmniParser)</strong></summary>

| Tool | Description |
|------|-------------|
| `mobile_find_elements` | **Primary tool** — screenshot → OmniParser → tap coordinates |
| `mobile_screenshot` | Take a screenshot (resized for LLM, max 1568px) |
| `mobile_save_screenshot` | Save screenshot to file |
| `mobile_parse_image` | Parse an existing image file |

</details>

<details open>
<summary><strong>Interaction</strong></summary>

| Tool | Description |
|------|-------------|
| `mobile_tap` | Tap an element by ID (from `find_elements`) |
| `mobile_double_tap` | Double-tap an element by ID |
| `mobile_long_press` | Long press an element by ID |
| `mobile_swipe` | Swipe in a direction (up / down / left / right) |
| `mobile_type_text` | Type text into the focused element |
| `mobile_press_button` | Press a hardware button (home / back / etc.) |

</details>

<details open>
<summary><strong>Device Management</strong></summary>

| Tool | Description |
|------|-------------|
| `mobile_list_devices` | List available devices and simulators |
| `mobile_get_screen_size` | Get device screen size |
| `mobile_list_apps` | List installed apps |
| `mobile_launch_app` | Launch an app by bundle ID |
| `mobile_terminate_app` | Terminate a running app |
| `mobile_open_url` | Open a URL in the default browser |

</details>

## Architecture

No dependency on mobile-mcp server. Directly controls devices via platform-native APIs:

| Platform | Device Discovery | Interactions | Screenshots | App Management |
|----------|-----------------|--------------|-------------|----------------|
| **iOS** | mobilecli (npx) | WebDriverAgent HTTP API | WDA `/screenshot` | `xcrun simctl` |
| **Android** | mobilecli (npx) | `adb shell input` | `adb exec-out screencap` | `adb shell am/pm` |

```
mobile-parser (MCP Server)
├── server.py          → FastMCP server with 16 tools
├── coordinator.py     → Screenshot → OmniParser → coordinate conversion
├── mobile_client.py   → Device control (iOS: WDA, Android: adb)
├── mobilecli.py       → mobilecli wrapper (npx auto-download)
├── wda.py             → WebDriverAgent HTTP client
└── parser.py          → OmniParser (YOLO + Florence-2 + EasyOCR)
```

## Configuration

| Environment Variable | Description | Default |
|----------------------|-------------|---------|
| `OMNIPARSER_WEIGHTS_DIR` | Model weights directory | `~/.cache/omniparser` |
| `OMNIPARSER_DEVICE` | Inference device (`cuda` / `mps` / `cpu`) | Auto-detect |
| `MOBILECLI_PATH` | mobilecli binary path | npx auto-download |

## License

[AGPL-3.0](LICENSE) — due to the [ultralytics](https://github.com/ultralytics/ultralytics) (YOLOv8) dependency.
