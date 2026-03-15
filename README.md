# mobile-parser

Mobile testing MCP server that combines [OmniParser](https://github.com/microsoft/OmniParser) UI element detection with device control via [mobile-mcp](https://github.com/nicholasyan/mobile-mcp).

OmniParser detects UI elements directly from screenshots, making it accurate even for apps where traditional accessibility-tree-based coordinate estimation fails (e.g., Flutter WebView apps).

## Quick Start

### Add to Claude Code

```bash
claude mcp add mobile-parser -- uvx --from "git+https://github.com/mi6ock/mobile-parser.git" mobile-parser
```

### Prerequisites

- **Python 3.10+** (managed by uv automatically)
- **Node.js / npm** (for mobile-mcp subprocess)
- **Xcode + iOS Simulator** (for iOS device control)

### First Run

On the first tool call, OmniParser models (~1.5GB) are automatically downloaded from HuggingFace (`microsoft/OmniParser-v2.0`) to `~/.cache/omniparser/`.

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
1. Takes a screenshot of the device
2. Runs OmniParser to detect all UI elements (text + icons)
3. Converts pixel coordinates to logical screen coordinates

The returned `tap_x`/`tap_y` can be passed directly to `mobile_tap()`.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OMNIPARSER_WEIGHTS_DIR` | Override model weights directory | `~/.cache/omniparser` |
| `OMNIPARSER_DEVICE` | Force inference device (`cuda`/`mps`/`cpu`) | Auto-detect |

## Testing with sample_app

The [sample_app](https://github.com/mi6ock/mcp_sandbox/tree/main/sample_app) is a Flutter WebView app where traditional accessibility-based coordinate estimation tends to be inaccurate. This MCP uses OmniParser's vision-based approach, which detects elements directly from screenshots and provides accurate tap coordinates even in these challenging scenarios.

## Architecture

```
mobile-parser (MCP Server)
├── server.py          → FastMCP server with 16 tools
├── coordinator.py     → Screenshot → OmniParser → coordinate conversion pipeline
├── mobile_client.py   → Subprocess MCP client for @mobilenext/mobile-mcp
└── parser.py          → OmniParser (YOLO + Florence-2 + EasyOCR)
```

## License

MIT
