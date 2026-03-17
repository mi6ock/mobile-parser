# mobile-parser

Mobile testing MCP server that combines [OmniParser](https://github.com/microsoft/OmniParser) UI element detection with direct device control.

OmniParser detects UI elements directly from screenshots, making it accurate even for apps where traditional accessibility-tree-based coordinate estimation fails (e.g., Flutter WebView apps).

**Supports both iOS and Android.**

## Quick Start

### Add to Claude Code

```bash
claude mcp add mobile-parser -- uvx --from "git+https://github.com/mi6ock/mobile-parser.git" mobile-parser
```

### Prerequisites

- **Python 3.10+** (managed by uv automatically)
- **Node.js / npm** (for mobilecli — auto-downloaded via npx, no pre-install needed)

#### iOS
- **Xcode + iOS Simulator**
- **WebDriverAgent** installed on the simulator
  - See: [Setup for iOS Simulator](https://github.com/nicholasyan/mobile-mcp/wiki/Setup-for-iOS-Simulator)

#### Android
- **Android SDK** (adb in PATH or `ANDROID_HOME` set)
- **Emulator or device** connected via adb

### What gets auto-downloaded

| Component | When | Size |
|-----------|------|------|
| Python packages (torch, etc.) | `claude mcp add` 時 | ~2GB |
| mobilecli binary | 初回デバイス操作時 (npx) | ~20MB |
| OmniParser models | 初回 `mobile_find_elements` 時 | ~1.5GB |
| Florence-2 processor | 初回アイコンキャプション時 | ~500MB |

## Architecture

No dependency on mobile-mcp server. Directly uses:

| Platform | Device Discovery | Interactions | Screenshots | App Management |
|----------|-----------------|--------------|-------------|----------------|
| **iOS** | mobilecli (npx) | WebDriverAgent HTTP API | WDA `/screenshot` | xcrun simctl |
| **Android** | mobilecli (npx) | `adb shell input` | `adb exec-out screencap` | `adb shell am/pm` |

```
mobile-parser (MCP Server)
├── server.py          → FastMCP server with 16 tools
├── coordinator.py     → Screenshot → OmniParser → coordinate conversion pipeline
├── mobile_client.py   → Device control (iOS: WDA + simctl, Android: adb)
├── mobilecli.py       → mobilecli wrapper (npx auto-download)
├── wda.py             → WebDriverAgent HTTP client (iOS)
└── parser.py          → OmniParser (YOLO + Florence-2 + EasyOCR)
```

## Tools (16 total)

### Device Management
| Tool | Description |
|------|-------------|
| `mobile_list_devices` | List all available devices and simulators |
| `mobile_get_screen_size` | Get device screen size in pixels |
| `mobile_list_apps` | List installed apps |
| `mobile_launch_app` | Launch an app |
| `mobile_terminate_app` | Terminate an app |
| `mobile_open_url` | Open a URL in the browser |

### Interaction
| Tool | Description |
|------|-------------|
| `mobile_tap` | Tap at coordinates |
| `mobile_double_tap` | Double-tap at coordinates |
| `mobile_long_press` | Long press at coordinates |
| `mobile_swipe` | Swipe in a direction |
| `mobile_type_text` | Type text into focused element |
| `mobile_press_button` | Press hardware button |

### Screen Analysis (OmniParser)
| Tool | Description |
|------|-------------|
| `mobile_screenshot` | Take a screenshot (resized for LLM, max 1568px) |
| `mobile_save_screenshot` | Save screenshot to file |
| `mobile_find_elements` | **Primary tool**: Screenshot → OmniParser → tap coordinates |
| `mobile_parse_image` | Parse an existing image file |

## Typical Workflow

```
1. mobile_find_elements(device="...") → get elements with tap coordinates
2. mobile_tap(device="...", x=tap_x, y=tap_y) → tap on the element
```

`mobile_find_elements` handles the full pipeline:
1. Takes a screenshot of the device
2. Runs OmniParser to detect all UI elements (text + icons)
3. Converts pixel coordinates to logical screen coordinates

The returned `tap_x`/`tap_y` can be passed directly to `mobile_tap()`.

All images returned to the LLM are resized to max 1568px (long edge) to prevent image size errors.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OMNIPARSER_WEIGHTS_DIR` | Override model weights directory | `~/.cache/omniparser` |
| `OMNIPARSER_DEVICE` | Force inference device (`cuda`/`mps`/`cpu`) | Auto-detect |
| `MOBILECLI_PATH` | Override mobilecli binary path | npx auto-download |

## License

MIT
