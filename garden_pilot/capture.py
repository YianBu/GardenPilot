"""Window capture through GDI (PrintWindow + BitBlt)."""

from __future__ import annotations

import ctypes
import traceback

import cv2
import numpy as np
import win32con
import win32gui
import win32ui

from .window import GameWindow

PW_RENDERFULLCONTENT = 0x00000002


class WindowCapture:
    def __init__(self, window: GameWindow, screen: tuple[int, int] = (1920, 1080)) -> None:
        self.window = window
        self.screen_width, self.screen_height = screen
        self._window_dc = None
        self._source_dc = None
        self._memory_dc = None
        self._bitmap = None
        self._size: tuple[int, int] = (0, 0)
        self.last_black_frame = False
        self.last_error: str | None = None

    def _ensure_surfaces(self, width: int, height: int) -> None:
        if self._bitmap is not None and self._size == (width, height):
            return
        self.close()
        self._window_dc = win32gui.GetWindowDC(self.window.hwnd)
        self._source_dc = win32ui.CreateDCFromHandle(self._window_dc)
        self._memory_dc = self._source_dc.CreateCompatibleDC()
        self._bitmap = win32ui.CreateBitmap()
        self._bitmap.CreateCompatibleBitmap(self._source_dc, width, height)
        self._memory_dc.SelectObject(self._bitmap)
        self._size = (width, height)

    def grab(self) -> np.ndarray | None:
        if not self.window.valid:
            return None
        window_width, window_height = self.window.window_rect()[2:]
        client_width, client_height = self.window.client_rect()
        offset_x, offset_y = self.window.client_offset()
        if window_width <= 0 or window_height <= 0 or client_width <= 0 or client_height <= 0:
            return None

        # The destination bitmap is client sized so BitBlt only copies the
        # game viewport, matching how ok-ww's BitBlt capture works.
        self._ensure_surfaces(client_width, client_height)
        try:
            ctypes.windll.user32.PrintWindow(
                self.window.hwnd, self._source_dc.GetSafeHdc(), PW_RENDERFULLCONTENT
            )
            self._memory_dc.BitBlt(
                (0, 0),
                (client_width, client_height),
                self._source_dc,
                (offset_x, offset_y),
                win32con.SRCCOPY,
            )
            bits = self._bitmap.GetBitmapBits(True)
            frame = np.frombuffer(bits, dtype=np.uint8)
            frame = frame.reshape((client_height, client_width, 4))
        except Exception:
            self.last_error = traceback.format_exc()
            return None

        frame = np.ascontiguousarray(frame[:, :, :3])
        self.last_black_frame = bool(frame.size) and float(frame.mean()) < 2.0 and float(frame.std()) < 2.0
        if (client_width, client_height) != (self.screen_width, self.screen_height):
            frame = cv2.resize(
                frame, (self.screen_width, self.screen_height), interpolation=cv2.INTER_AREA
            )
        return frame

    def close(self) -> None:
        for dc in (self._memory_dc, self._source_dc):
            if dc is not None:
                try:
                    dc.DeleteDC()
                except Exception:
                    pass
        if self._window_dc is not None:
            try:
                win32gui.ReleaseDC(self.window.hwnd, self._window_dc)
            except Exception:
                pass
        if self._bitmap is not None:
            try:
                win32gui.DeleteObject(self._bitmap.GetHandle())
            except Exception:
                pass
        self._window_dc = None
        self._source_dc = None
        self._memory_dc = None
        self._bitmap = None
        self._size = (0, 0)
