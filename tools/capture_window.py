"""Save a screenshot of any window by hwnd (development helper)."""

from __future__ import annotations

import ctypes
import sys

import win32gui
import win32ui
from PIL import Image


def capture(hwnd: int, path: str) -> None:
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width, height = right - left, bottom - top
    window_dc = win32gui.GetWindowDC(hwnd)
    source_dc = win32ui.CreateDCFromHandle(window_dc)
    memory_dc = source_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(source_dc, width, height)
    memory_dc.SelectObject(bitmap)
    ctypes.windll.user32.PrintWindow(hwnd, memory_dc.GetSafeHdc(), 2)
    info = bitmap.GetInfo()
    image = Image.frombuffer(
        "RGB", (info["bmWidth"], info["bmHeight"]), bitmap.GetBitmapBits(True), "raw", "BGRX", 0, 1
    )
    image.save(path)
    win32gui.DeleteObject(bitmap.GetHandle())
    memory_dc.DeleteDC()
    source_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, window_dc)
    print("saved", path, width, height)


if __name__ == "__main__":
    capture(int(sys.argv[1]), sys.argv[2])
