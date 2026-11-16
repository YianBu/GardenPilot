"""List visible top-level windows with pid and title (development helper)."""

from __future__ import annotations

import sys

import win32gui
import win32process


def main() -> None:
    wanted = {int(arg) for arg in sys.argv[1:]}

    def collect(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if wanted and pid not in wanted:
            return True
        title = win32gui.GetWindowText(hwnd)
        if title:
            print(hwnd, pid, repr(title), win32gui.GetClassName(hwnd))
        return True

    win32gui.EnumWindows(collect, None)


if __name__ == "__main__":
    main()
