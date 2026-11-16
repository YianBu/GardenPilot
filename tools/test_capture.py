"""Capture an arbitrary hwnd through WindowCapture to verify the GDI path."""

from __future__ import annotations

import sys
from pathlib import Path

import cv2

GARDEN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GARDEN_DIR))

from garden_pilot.capture import WindowCapture
from garden_pilot.window import GameWindow


def main() -> int:
    hwnd = int(sys.argv[1])
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else GARDEN_DIR / "logs" / "capture_test.png"
    window = GameWindow(hwnd, 0, "test", "test")
    capture = WindowCapture(window)
    try:
        frame = capture.grab()
    finally:
        capture.close()
    if frame is None:
        print("capture failed")
        if capture.last_error:
            print(capture.last_error)
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output), frame)
    print("frame", frame.shape, "mean", round(float(frame.mean()), 1), "black", capture.last_black_frame)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
