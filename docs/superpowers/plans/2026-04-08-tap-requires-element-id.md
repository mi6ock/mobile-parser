# Tap Requires Element ID Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** タップ系操作（tap / double_tap / long_press）を、`find_elements` で取得した要素 ID 必須に変更し、座標直指定によるバイパスを防ぐ。

**Architecture:** `server.py` にデバイスごとの要素レジストリ（`_element_registry`）を追加する。`find_elements` 実行時にレジストリを更新し、タップ系ツールは要素 ID でレジストリを参照して座標を解決する。座標を直接受け取るインターフェースは廃止する。

**Tech Stack:** Python, FastMCP, pytest, pytest-asyncio

---

### File Structure

| Action | Path | Responsibility |
|--------|------|---------------|
| Modify | `src/mobile_parser/server.py` | 要素レジストリ追加、tap/double_tap/long_press のシグネチャ変更、find_elements でレジストリ更新 |
| Modify | `tests/conftest.py` | mock_mobile fixture に変更不要（MobileClient のインターフェースは変更しない） |
| Modify | `tests/test_proxy_tools.py` | タップ系テストを ID ベースに書き換え、バリデーションエラーのテスト追加 |
| Modify | `tests/test_helpers.py` | `_format_find_elements` のテストに利用案内テキストの変更を反映 |

---

### Task 1: 要素レジストリの追加と find_elements でのレジストリ更新

**Files:**
- Modify: `src/mobile_parser/server.py:28-46` (グローバル変数・ヘルパー関数)
- Modify: `src/mobile_parser/server.py:232-268` (find_elements)
- Test: `tests/test_proxy_tools.py`

- [ ] **Step 1: 要素レジストリのテストを書く**

`tests/test_proxy_tools.py` に以下を追加:

```python
async def test_find_elements_populates_registry(mock_mobile, mock_coordinator):
    """find_elements がレジストリに要素を保存する。"""
    import mobile_parser.server as srv
    srv._mobile = mock_mobile
    srv._coordinator = mock_coordinator
    await srv.mobile_find_elements("dev1")
    registry = srv._element_registry
    assert "dev1" in registry
    assert registry["dev1"][0] == (215, 466)
```

`tests/conftest.py` に `mock_coordinator` fixture を追加:

```python
@pytest.fixture
def mock_coordinator():
    """Return a mock Coordinator that returns pre-built elements."""
    import base64
    from unittest.mock import AsyncMock, MagicMock

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
        "annotated_image": base64.b64encode(b"fake_png").decode(),
        "screenshot_path": "/tmp/screenshot.png",
    })
    return coord
```

- [ ] **Step 2: テストが FAIL することを確認**

Run: `cd /Users/m66/mobile-parser && python -m pytest tests/test_proxy_tools.py::test_find_elements_populates_registry -v`
Expected: FAIL (`_element_registry` が存在しない)

- [ ] **Step 3: レジストリの追加と find_elements の更新を実装**

`src/mobile_parser/server.py` を変更:

グローバル変数に追加 (既存の `_coordinator` の下):

```python
_element_registry: dict[str, dict[int, tuple[float, float]]] = {}
```

`mobile_find_elements` 関数内、`result = await coordinator.find_elements(...)` の後、`text = _format_find_elements(result)` の前に追加:

```python
    # Update element registry for this device
    _element_registry[device] = {
        elem["id"]: (elem["tap_x"], elem["tap_y"])
        for elem in result["elements"]
    }
```

- [ ] **Step 4: テストが PASS することを確認**

Run: `cd /Users/m66/mobile-parser && python -m pytest tests/test_proxy_tools.py::test_find_elements_populates_registry -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
cd /Users/m66/mobile-parser
git add src/mobile_parser/server.py tests/test_proxy_tools.py tests/conftest.py
git commit -m "feat: add element registry populated by find_elements"
```

---

### Task 2: mobile_tap を要素 ID ベースに変更

**Files:**
- Modify: `src/mobile_parser/server.py:118-127` (mobile_tap)
- Test: `tests/test_proxy_tools.py`

- [ ] **Step 1: ID ベースの tap テストを書く**

`tests/test_proxy_tools.py` の既存 `test_mobile_tap` を以下に書き換え、追加テストも記述:

```python
async def test_mobile_tap(mock_mobile, mock_coordinator):
    """find_elements で取得した ID を指定してタップできる。"""
    import mobile_parser.server as srv
    srv._mobile = mock_mobile
    srv._coordinator = mock_coordinator
    # まず find_elements でレジストリに登録
    await srv.mobile_find_elements("dev1")
    # ID 0 でタップ
    result = await srv.mobile_tap("dev1", 0)
    mock_mobile.tap.assert_called_once_with("dev1", 215, 466)
    assert "Tapped" in result


async def test_mobile_tap_invalid_id(mock_mobile, mock_coordinator):
    """存在しない ID を指定するとエラーになる。"""
    import mobile_parser.server as srv
    srv._mobile = mock_mobile
    srv._coordinator = mock_coordinator
    await srv.mobile_find_elements("dev1")
    result = await srv.mobile_tap("dev1", 999)
    assert "not found" in result.lower() or "error" in result.lower()


async def test_mobile_tap_no_find_elements(mock_mobile):
    """find_elements を呼ばずにタップするとエラーになる。"""
    import mobile_parser.server as srv
    srv._mobile = mock_mobile
    result = await srv.mobile_tap("dev1", 0)
    assert "find_elements" in result.lower() or "error" in result.lower()
```

- [ ] **Step 2: テストが FAIL することを確認**

Run: `cd /Users/m66/mobile-parser && python -m pytest tests/test_proxy_tools.py::test_mobile_tap tests/test_proxy_tools.py::test_mobile_tap_invalid_id tests/test_proxy_tools.py::test_mobile_tap_no_find_elements -v`
Expected: FAIL (mobile_tap のシグネチャが x, y のまま)

- [ ] **Step 3: mobile_tap を ID ベースに実装**

`src/mobile_parser/server.py` の `mobile_tap` を以下に置換:

```python
@mcp.tool()
async def mobile_tap(device: str, element_id: int) -> str:
    """Tap on a UI element identified by its ID from mobile_find_elements.

    You MUST call mobile_find_elements first to detect elements and obtain IDs.

    Args:
        device: Device identifier
        element_id: Element ID returned by mobile_find_elements
    """
    coords = _element_registry.get(device, {}).get(element_id)
    if coords is None:
        if device not in _element_registry:
            return (
                "Error: No elements registered for this device. "
                "Call mobile_find_elements first to detect UI elements."
            )
        return (
            f"Error: Element ID {element_id} not found. "
            f"Valid IDs: {sorted(_element_registry[device].keys())}. "
            f"Call mobile_find_elements to refresh."
        )
    x, y = coords
    return await _get_mobile().tap(device, x, y)
```

- [ ] **Step 4: テストが PASS することを確認**

Run: `cd /Users/m66/mobile-parser && python -m pytest tests/test_proxy_tools.py::test_mobile_tap tests/test_proxy_tools.py::test_mobile_tap_invalid_id tests/test_proxy_tools.py::test_mobile_tap_no_find_elements -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
cd /Users/m66/mobile-parser
git add src/mobile_parser/server.py tests/test_proxy_tools.py
git commit -m "feat: require element ID for mobile_tap instead of raw coordinates"
```

---

### Task 3: mobile_double_tap を要素 ID ベースに変更

**Files:**
- Modify: `src/mobile_parser/server.py:130-139` (mobile_double_tap)
- Test: `tests/test_proxy_tools.py`

- [ ] **Step 1: ID ベースの double_tap テストを書く**

`tests/test_proxy_tools.py` の既存 `test_mobile_double_tap` を以下に書き換え:

```python
async def test_mobile_double_tap(mock_mobile, mock_coordinator):
    """find_elements で取得した ID を指定してダブルタップできる。"""
    import mobile_parser.server as srv
    srv._mobile = mock_mobile
    srv._coordinator = mock_coordinator
    await srv.mobile_find_elements("dev1")
    result = await srv.mobile_double_tap("dev1", 0)
    mock_mobile.double_tap.assert_called_once_with("dev1", 215, 466)
    assert "Double-tapped" in result


async def test_mobile_double_tap_no_find_elements(mock_mobile):
    """find_elements なしでダブルタップするとエラー。"""
    import mobile_parser.server as srv
    srv._mobile = mock_mobile
    result = await srv.mobile_double_tap("dev1", 0)
    assert "find_elements" in result.lower() or "error" in result.lower()
```

- [ ] **Step 2: テストが FAIL することを確認**

Run: `cd /Users/m66/mobile-parser && python -m pytest tests/test_proxy_tools.py::test_mobile_double_tap tests/test_proxy_tools.py::test_mobile_double_tap_no_find_elements -v`
Expected: FAIL

- [ ] **Step 3: mobile_double_tap を ID ベースに実装**

`src/mobile_parser/server.py` の `mobile_double_tap` を以下に置換:

```python
@mcp.tool()
async def mobile_double_tap(device: str, element_id: int) -> str:
    """Double-tap on a UI element identified by its ID from mobile_find_elements.

    You MUST call mobile_find_elements first to detect elements and obtain IDs.

    Args:
        device: Device identifier
        element_id: Element ID returned by mobile_find_elements
    """
    coords = _element_registry.get(device, {}).get(element_id)
    if coords is None:
        if device not in _element_registry:
            return (
                "Error: No elements registered for this device. "
                "Call mobile_find_elements first to detect UI elements."
            )
        return (
            f"Error: Element ID {element_id} not found. "
            f"Valid IDs: {sorted(_element_registry[device].keys())}. "
            f"Call mobile_find_elements to refresh."
        )
    x, y = coords
    return await _get_mobile().double_tap(device, x, y)
```

- [ ] **Step 4: テストが PASS することを確認**

Run: `cd /Users/m66/mobile-parser && python -m pytest tests/test_proxy_tools.py::test_mobile_double_tap tests/test_proxy_tools.py::test_mobile_double_tap_no_find_elements -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
cd /Users/m66/mobile-parser
git add src/mobile_parser/server.py tests/test_proxy_tools.py
git commit -m "feat: require element ID for mobile_double_tap"
```

---

### Task 4: mobile_long_press を要素 ID ベースに変更

**Files:**
- Modify: `src/mobile_parser/server.py:142-155` (mobile_long_press)
- Test: `tests/test_proxy_tools.py`

- [ ] **Step 1: ID ベースの long_press テストを書く**

`tests/test_proxy_tools.py` の既存 `test_mobile_long_press_default` と `test_mobile_long_press_with_duration` を以下に書き換え:

```python
async def test_mobile_long_press_default(mock_mobile, mock_coordinator):
    """find_elements で取得した ID でロングプレスできる（デフォルト duration）。"""
    import mobile_parser.server as srv
    srv._mobile = mock_mobile
    srv._coordinator = mock_coordinator
    await srv.mobile_find_elements("dev1")
    result = await srv.mobile_long_press("dev1", 0)
    mock_mobile.long_press.assert_called_once_with("dev1", 215, 466, 500)
    assert "Long-pressed" in result


async def test_mobile_long_press_with_duration(mock_mobile, mock_coordinator):
    """duration を指定してロングプレスできる。"""
    import mobile_parser.server as srv
    srv._mobile = mock_mobile
    srv._coordinator = mock_coordinator
    await srv.mobile_find_elements("dev1")
    result = await srv.mobile_long_press("dev1", 0, 1000)
    mock_mobile.long_press.assert_called_once_with("dev1", 215, 466, 1000)


async def test_mobile_long_press_no_find_elements(mock_mobile):
    """find_elements なしでロングプレスするとエラー。"""
    import mobile_parser.server as srv
    srv._mobile = mock_mobile
    result = await srv.mobile_long_press("dev1", 0)
    assert "find_elements" in result.lower() or "error" in result.lower()
```

- [ ] **Step 2: テストが FAIL することを確認**

Run: `cd /Users/m66/mobile-parser && python -m pytest tests/test_proxy_tools.py::test_mobile_long_press_default tests/test_proxy_tools.py::test_mobile_long_press_with_duration tests/test_proxy_tools.py::test_mobile_long_press_no_find_elements -v`
Expected: FAIL

- [ ] **Step 3: mobile_long_press を ID ベースに実装**

`src/mobile_parser/server.py` の `mobile_long_press` を以下に置換:

```python
@mcp.tool()
async def mobile_long_press(
    device: str, element_id: int, duration: float | None = None
) -> str:
    """Long press on a UI element identified by its ID from mobile_find_elements.

    You MUST call mobile_find_elements first to detect elements and obtain IDs.

    Args:
        device: Device identifier
        element_id: Element ID returned by mobile_find_elements
        duration: Duration in milliseconds (default 500ms)
    """
    coords = _element_registry.get(device, {}).get(element_id)
    if coords is None:
        if device not in _element_registry:
            return (
                "Error: No elements registered for this device. "
                "Call mobile_find_elements first to detect UI elements."
            )
        return (
            f"Error: Element ID {element_id} not found. "
            f"Valid IDs: {sorted(_element_registry[device].keys())}. "
            f"Call mobile_find_elements to refresh."
        )
    x, y = coords
    d = duration if duration is not None else 500
    return await _get_mobile().long_press(device, x, y, d)
```

- [ ] **Step 4: テストが PASS することを確認**

Run: `cd /Users/m66/mobile-parser && python -m pytest tests/test_proxy_tools.py::test_mobile_long_press_default tests/test_proxy_tools.py::test_mobile_long_press_with_duration tests/test_proxy_tools.py::test_mobile_long_press_no_find_elements -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
cd /Users/m66/mobile-parser
git add src/mobile_parser/server.py tests/test_proxy_tools.py
git commit -m "feat: require element ID for mobile_long_press"
```

---

### Task 5: レジストリリセットと全テスト通過確認

**Files:**
- Modify: `tests/conftest.py:40-47` (reset_server_globals)
- Test: 全テストファイル

- [ ] **Step 1: レジストリリセットのテストを書く**

`tests/test_proxy_tools.py` に追加:

```python
async def test_find_elements_resets_registry(mock_mobile, mock_coordinator):
    """find_elements を再度呼ぶと古いレジストリが置き換わる。"""
    import mobile_parser.server as srv
    srv._mobile = mock_mobile
    srv._coordinator = mock_coordinator
    # 古いレジストリを手動設定
    srv._element_registry["dev1"] = {99: (100, 200)}
    # find_elements で更新
    await srv.mobile_find_elements("dev1")
    assert 99 not in srv._element_registry["dev1"]
    assert 0 in srv._element_registry["dev1"]
```

- [ ] **Step 2: テストが PASS することを確認**

Run: `cd /Users/m66/mobile-parser && python -m pytest tests/test_proxy_tools.py::test_find_elements_resets_registry -v`
Expected: PASS (Task 1 の実装で dict 内包表記による上書きが行われているため)

- [ ] **Step 3: conftest.py の reset_server_globals にレジストリリセットを追加**

`tests/conftest.py` の `reset_server_globals` を更新:

```python
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
```

- [ ] **Step 4: 全テストが PASS することを確認**

Run: `cd /Users/m66/mobile-parser && python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 5: コミット**

```bash
cd /Users/m66/mobile-parser
git add tests/conftest.py tests/test_proxy_tools.py
git commit -m "feat: reset element registry between tests, verify full test suite"
```
