# mobile-parser

Mobile testing MCP server that combines [OmniParser](https://github.com/microsoft/OmniParser) UI element detection with direct device control.

OmniParser detects UI elements directly from screenshots, making it accurate even for apps where traditional accessibility-tree-based coordinate estimation fails (e.g., Flutter WebView apps).

## Architecture

No dependency on mobile-mcp server. Directly uses:
- **mobilecli binary** (`@mobilenext/mobilecli`) for device discovery
- **WebDriverAgent HTTP API** for screen interactions (tap, swipe, type)
- **xcrun simctl** for iOS simulator app management
- **OmniParser** (YOLO + Florence-2 + EasyOCR) for vision-based UI element detection

```
mobile-parser (MCP Server)
├── server.py          → FastMCP server with 16 tools
├── coordinator.py     → Screenshot → OmniParser → coordinate conversion pipeline
├── mobile_client.py   → Direct device control (mobilecli + WDA + xcrun simctl)
├── mobilecli.py       → @mobilenext/mobilecli binary wrapper
├── wda.py             → WebDriverAgent HTTP client
└── parser.py          → OmniParser (YOLO + Florence-2 + EasyOCR)
```

## Quick Start

### Add to Claude Code

```bash
claude mcp add mobile-parser -- uvx --from "git+https://github.com/mi6ock/mobile-parser.git" mobile-parser
```

### Prerequisites

- **Python 3.10+** (managed by uv automatically)
- **Node.js / npm** (for mobilecli binary)
- **Xcode + iOS Simulator** (for iOS device control)
- **WebDriverAgent** installed on the simulator
  - See: [Setup for iOS Simulator](https://github.com/nicholasyan/mobile-mcp/wiki/Setup-for-iOS-Simulator)
- **mobilecli binary**: `npm install -g @mobilenext/mobilecli`

### First Run

On the first tool call involving OmniParser, models (~1.5GB) are automatically downloaded from HuggingFace (`microsoft/OmniParser-v2.0`) to `~/.cache/omniparser/`.

WebDriverAgent is auto-started on iOS simulators if installed. If WDA is already running, it's reused.

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
| `mobile_tap` | Tap at coordinates (logical pixels) |
| `mobile_double_tap` | Double-tap at coordinates |
| `mobile_long_press` | Long press at coordinates |
| `mobile_swipe` | Swipe in a direction |
| `mobile_type_text` | Type text into focused element |
| `mobile_press_button` | Press hardware button |

### Screen Analysis (OmniParser)
| Tool | Description |
|------|-------------|
| `mobile_screenshot` | Take a screenshot (returns base64 image) |
| `mobile_save_screenshot` | Save screenshot to file |
| `mobile_find_elements` | **Primary tool**: Screenshot → OmniParser → tap coordinates |
| `mobile_parse_image` | Parse an existing image file |

## Typical Workflow

```
1. mobile_find_elements(device="...") → get elements with tap coordinates
2. mobile_tap(device="...", x=tap_x, y=tap_y) → tap on the element
```

`mobile_find_elements` handles the full pipeline:
1. Takes a screenshot of the device via WDA
2. Runs OmniParser to detect all UI elements (text + icons)
3. Converts pixel coordinates to logical screen coordinates

The returned `tap_x`/`tap_y` can be passed directly to `mobile_tap()`.

## Testing with sample_app

The [sample_app](https://github.com/mi6ock/mcp_sandbox/tree/main/sample_app) is a Flutter WebView app where traditional accessibility-based coordinate estimation tends to be inaccurate.

To test:

1. Boot an iOS Simulator
2. Build and install sample_app on the simulator:
   ```bash
   cd sample_app && flutter run
   ```
3. Add mobile-parser to Claude Code:
   ```bash
   claude mcp add mobile-parser -- uvx --from "git+https://github.com/mi6ock/mobile-parser.git" mobile-parser
   ```
4. Use `mobile_find_elements` to detect UI elements and verify tap coordinates are accurate within the WebView

The OmniParser vision-based approach detects elements directly from screenshots, providing accurate tap coordinates even in challenging scenarios where accessibility trees are unreliable.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OMNIPARSER_WEIGHTS_DIR` | Override model weights directory | `~/.cache/omniparser` |
| `OMNIPARSER_DEVICE` | Force inference device (`cuda`/`mps`/`cpu`) | Auto-detect |
| `MOBILECLI_PATH` | Override mobilecli binary path | Auto-detect |

## License

MIT
