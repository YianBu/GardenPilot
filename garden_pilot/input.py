"""Background keyboard and mouse input through PostMessage."""

from __future__ import annotations

import time

import win32api
import win32con
import win32gui

VK_CODES = {
    "esc": 0x1B,
    "escape": 0x1B,
    "alt": 0x12,
    "shift": 0x10,
    "ctrl": 0x11,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "space": 0x20,
    "enter": 0x0D,
    "tab": 0x09,
}


def _vk(name: str) -> int:
    key = str(name).lower()
    if key in VK_CODES:
        return VK_CODES[key]
    if len(key) == 1:
        return win32api.VkKeyScan(key) & 0xFF
    raise KeyError(f"unknown key: {name}")


class GameInput:
    """Posts window messages so the game does not need foreground focus."""

    def __init__(self, hwnd: int, client_size, use_foreground: bool = False) -> None:
        self.hwnd = hwnd
        self.client_size = client_size
        self.use_foreground = use_foreground
        self._local = (0, 0)

    def activate(self) -> None:
        try:
            win32gui.PostMessage(self.hwnd, win32con.WM_ACTIVATE, win32con.WA_ACTIVE, 0)
        except Exception:
            pass

    def _target_and_local(self, x: int, y: int) -> tuple[int, int, int]:
        screen_x, screen_y = win32gui.ClientToScreen(self.hwnd, (int(x), int(y)))
        target = self.hwnd
        try:
            hit = win32gui.WindowFromPoint((screen_x, screen_y))
            if hit and hit != self.hwnd and win32gui.GetAncestor(hit, win32con.GA_ROOT) == self.hwnd:
                target = hit
        except Exception:
            pass
        local_x, local_y = win32gui.ScreenToClient(target, (screen_x, screen_y))
        return target, int(local_x), int(local_y)

    def click_norm(self, x_ratio: float, y_ratio: float, down_time: float = 0.2, after_sleep: float = 0.0) -> None:
        width, height = self.client_size()
        self.click_px(round(x_ratio * width), round(y_ratio * height), down_time, after_sleep)

    def click_px(self, x: int, y: int, down_time: float = 0.2, after_sleep: float = 0.0) -> None:
        if self.use_foreground:
            self._foreground_click(x, y)
        else:
            self.activate()
            target, local_x, local_y = self._target_and_local(x, y)
            position = win32api.MAKELONG(local_x, local_y)
            win32gui.PostMessage(target, win32con.WM_MOUSEMOVE, 0, position)
            time.sleep(0.02)
            win32gui.PostMessage(target, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, position)
            time.sleep(down_time)
            win32gui.PostMessage(target, win32con.WM_LBUTTONUP, 0, position)
        if after_sleep > 0:
            time.sleep(after_sleep)

    def _foreground_click(self, x: int, y: int) -> None:
        try:
            win32gui.SetForegroundWindow(self.hwnd)
        except Exception:
            pass
        screen_x, screen_y = win32gui.ClientToScreen(self.hwnd, (int(x), int(y)))
        win32api.SetCursorPos((screen_x, screen_y))
        time.sleep(0.05)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.05)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def key_down(self, name: str) -> None:
        vk = _vk(name)
        scan = win32api.MapVirtualKey(vk, 0)
        win32gui.PostMessage(self.hwnd, win32con.WM_KEYDOWN, vk, (scan << 16) | 1)

    def key_up(self, name: str) -> None:
        vk = _vk(name)
        scan = win32api.MapVirtualKey(vk, 0)
        win32gui.PostMessage(self.hwnd, win32con.WM_KEYUP, vk, (scan << 16) | 1 | (1 << 30) | (1 << 31))

    def send_key(self, name: str, down_time: float = 0.05) -> None:
        self.activate()
        self.key_down(name)
        time.sleep(down_time)
        self.key_up(name)

    def back(self) -> None:
        self.send_key("esc")

    def alt_click_norm(self, x_ratio: float, y_ratio: float, after_sleep: float = 0.0) -> None:
        self.activate()
        self.key_down("alt")
        time.sleep(0.05)
        self.click_norm(x_ratio, y_ratio, down_time=0.05)
        time.sleep(0.02)
        self.key_up("alt")
        if after_sleep > 0:
            time.sleep(after_sleep)
