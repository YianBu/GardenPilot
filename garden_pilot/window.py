"""Locate the Wuthering Waves window and report its client geometry."""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass

import win32con
import win32gui
import win32process

GAME_EXE = "client-win64-shipping.exe"
GAME_TITLE_HINTS = ("鸣潮", "wuthering waves", "鳴潮")


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


@dataclass
class GameWindow:
    hwnd: int
    pid: int
    title: str
    class_name: str

    @property
    def valid(self) -> bool:
        return bool(self.hwnd) and bool(win32gui.IsWindow(self.hwnd))

    def window_rect(self) -> tuple[int, int, int, int]:
        left, top, right, bottom = win32gui.GetWindowRect(self.hwnd)
        return left, top, right - left, bottom - top

    def client_rect(self) -> tuple[int, int]:
        _, _, right, bottom = win32gui.GetClientRect(self.hwnd)
        return int(right), int(bottom)

    def client_offset(self) -> tuple[int, int]:
        left, top, _, _ = self.window_rect()
        client_x, client_y = win32gui.ClientToScreen(self.hwnd, (0, 0))
        return int(client_x - left), int(client_y - top)


def _process_path(pid: int) -> str:
    process_handle = None
    try:
        process_handle = win32process.OpenProcess(
            win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, pid
        )
        return win32process.GetModuleFileNameEx(process_handle, 0) or ""
    except Exception:
        return ""
    finally:
        if process_handle:
            try:
                win32process.CloseHandle(process_handle)
            except Exception:
                pass


def _iter_windows():
    windows: list[tuple[int, int, str, str]] = []

    def collect(hwnd: int, _param) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        class_name = win32gui.GetClassName(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if title or class_name:
            windows.append((hwnd, pid, title, class_name))
        return True

    win32gui.EnumWindows(collect, None)
    return windows


def find_game_window() -> GameWindow | None:
    """Return the game window, preferring the known executable name."""

    candidates: list[tuple[int, GameWindow]] = []
    for hwnd, pid, title, class_name in _iter_windows():
        exe = os.path.basename(_process_path(pid)).lower()
        score = 0
        if exe == GAME_EXE:
            score += 100
        if title.strip() and any(hint in title.lower() for hint in GAME_TITLE_HINTS):
            score += 50
        if class_name == "UnrealWindow":
            score += 30
        if score < 50:
            continue
        _, _, right, bottom = win32gui.GetClientRect(hwnd)
        if right < 320 or bottom < 180:
            continue
        candidates.append((score + right * bottom // 1_000_000, GameWindow(hwnd, pid, title, class_name)))

    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]
