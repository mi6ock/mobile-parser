# coding: utf-8
"""Tests for server tools - verifying they correctly delegate to MobileClient."""

import mobile_parser.server as srv


# ---------------------------------------------------------------------------
# Device management tools
# ---------------------------------------------------------------------------


async def test_mobile_list_devices(mock_mobile):
    srv._mobile = mock_mobile
    result = await srv.mobile_list_devices()
    mock_mobile.list_devices.assert_called_once()
    assert "iPhone 16 Pro" in result


async def test_mobile_get_screen_size(mock_mobile):
    srv._mobile = mock_mobile
    result = await srv.mobile_get_screen_size("dev1")
    mock_mobile.get_screen_size.assert_called_once_with("dev1")
    assert "430x932" in result


async def test_mobile_list_apps(mock_mobile):
    srv._mobile = mock_mobile
    result = await srv.mobile_list_apps("dev1")
    mock_mobile.list_apps.assert_called_once_with("dev1")
    assert "Safari" in result


async def test_mobile_launch_app(mock_mobile):
    srv._mobile = mock_mobile
    result = await srv.mobile_launch_app("dev1", "com.app")
    mock_mobile.launch_app.assert_called_once_with("dev1", "com.app")
    assert "Launched" in result


async def test_mobile_terminate_app(mock_mobile):
    srv._mobile = mock_mobile
    result = await srv.mobile_terminate_app("dev1", "com.app")
    mock_mobile.terminate_app.assert_called_once_with("dev1", "com.app")
    assert "Terminated" in result


async def test_mobile_open_url(mock_mobile):
    srv._mobile = mock_mobile
    result = await srv.mobile_open_url("dev1", "https://example.com")
    mock_mobile.open_url.assert_called_once_with("dev1", "https://example.com")
    assert "https://example.com" in result


# ---------------------------------------------------------------------------
# Interaction tools
# ---------------------------------------------------------------------------


async def test_mobile_tap(mock_mobile, mock_coordinator):
    """find_elements で取得した ID を指定してタップできる。"""
    import mobile_parser.server as srv
    srv._mobile = mock_mobile
    srv._coordinator = mock_coordinator
    await srv.mobile_find_elements("dev1")
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


async def test_mobile_swipe_simple(mock_mobile):
    srv._mobile = mock_mobile
    result = await srv.mobile_swipe("dev1", "up")
    mock_mobile.swipe.assert_called_once_with("dev1", "up", None, None, None)
    assert "Swiped" in result


async def test_mobile_swipe_full(mock_mobile):
    srv._mobile = mock_mobile
    result = await srv.mobile_swipe("dev1", "down", 100, 200, 500)
    mock_mobile.swipe.assert_called_once_with("dev1", "down", 100, 200, 500)


async def test_mobile_type_text(mock_mobile):
    srv._mobile = mock_mobile
    result = await srv.mobile_type_text("dev1", "hello", True)
    mock_mobile.type_text.assert_called_once_with("dev1", "hello", True)
    assert "Typed" in result


async def test_mobile_press_button(mock_mobile):
    srv._mobile = mock_mobile
    result = await srv.mobile_press_button("dev1", "HOME")
    mock_mobile.press_button.assert_called_once_with("dev1", "HOME")
    assert "Pressed HOME" in result


# ---------------------------------------------------------------------------
# Screenshot tools
# ---------------------------------------------------------------------------


async def test_mobile_screenshot(mock_mobile):
    srv._mobile = mock_mobile
    result = await srv.mobile_screenshot("dev1")
    mock_mobile.take_screenshot.assert_called_once_with("dev1")
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0] == "Screenshot taken"


async def test_mobile_save_screenshot(mock_mobile):
    srv._mobile = mock_mobile
    result = await srv.mobile_save_screenshot("dev1", "/tmp/x.png")
    mock_mobile.save_screenshot.assert_called_once_with("dev1", "/tmp/x.png")
    assert "/tmp/x.png" in result


# ---------------------------------------------------------------------------
# Element registry
# ---------------------------------------------------------------------------


async def test_find_elements_populates_registry(mock_mobile, mock_coordinator):
    """find_elements がレジストリに要素を保存する。"""
    import mobile_parser.server as srv
    srv._mobile = mock_mobile
    srv._coordinator = mock_coordinator
    await srv.mobile_find_elements("dev1")
    registry = srv._element_registry
    assert "dev1" in registry
    assert registry["dev1"][0] == (215, 466)


async def test_find_elements_resets_registry(mock_mobile, mock_coordinator):
    """find_elements を再度呼ぶと古いレジストリが置き換わる。"""
    import mobile_parser.server as srv
    srv._mobile = mock_mobile
    srv._coordinator = mock_coordinator
    srv._element_registry["dev1"] = {99: (100, 200)}
    await srv.mobile_find_elements("dev1")
    assert 99 not in srv._element_registry["dev1"]
    assert 0 in srv._element_registry["dev1"]
