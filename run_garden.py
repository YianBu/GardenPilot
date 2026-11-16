"""Standalone entry point for the weekly garden automation.

Usage:
    python run_garden.py                 # run the garden loop
    python run_garden.py --dry-run       # capture one frame and save it
    python run_garden.py --no-ocr        # skip the points OCR checks
    python run_garden.py --foreground    # use real cursor input instead of PostMessage
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import cv2

GARDEN_DIR = Path(__file__).resolve().parent
if str(GARDEN_DIR) not in sys.path:
    sys.path.insert(0, str(GARDEN_DIR))

from garden_pilot.capture import WindowCapture
from garden_pilot.features import TemplateSet
from garden_pilot.input import GameInput
from garden_pilot.paths import LOG_DIR, TEMPLATE_DIR
from garden_pilot.runner import LOGGER, GardenRunner
from garden_pilot.window import enable_dpi_awareness, find_game_window

HCENTER_FEATURES = (
    "monthly_card",
    "skip_dialog_check",
    "suisui_forte3",
    "message_dialog",
    "claim_stamina_sign",
    "skip_quest_confirm",
    "skip_quest_confirm_new",
    "login_close",
    "garden_confirm",
    "garden_continue_game",
    "garden_unpause",
    "garden_get_gold",
    "garden_get_purple",
    "garden_get_skip",
    "garden_not_interested_confirm",
    "garden_not_interested",
    "a_garden_back",
    "garden_get_confirm_gray",
    "the_garden_max",
    "garden_shop_close",
    "garden_new_stage",
    "a_garden_restart",
    "suisui_forte2",
    "e_forte",
    "f_break_full",
)

VCENTER_FEATURES = ("monthly_card", "skip_dialog_check")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="自动周常乐园（独立脚本）")
    parser.add_argument("--dry-run", action="store_true", help="只截图并保存，不执行任何点击")
    parser.add_argument("--no-ocr", action="store_true", help="不加载 OCR，跳过进度与结算判定")
    parser.add_argument("--foreground", action="store_true", help="使用前台鼠标点击（默认后台消息点击）")
    parser.add_argument("--window-wait", type=float, default=60, help="等待游戏窗口出现的最长秒数")
    parser.add_argument("--output", default=str(LOG_DIR / "garden_frame.png"), help="dry-run 截图保存路径")
    parser.add_argument("--verbose", action="store_true", help="输出调试日志")
    return parser.parse_args()


def wait_for_window(timeout: float):
    deadline = time.time() + timeout
    while time.time() < deadline:
        window = find_game_window()
        if window is not None:
            return window
        time.sleep(1)
    return None


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    LOGGER.setLevel(logging.DEBUG if args.verbose else logging.INFO)

    enable_dpi_awareness()
    print("等待鸣潮游戏窗口…")
    window = wait_for_window(args.window_wait)
    if window is None:
        print("没有找到游戏窗口：请先启动鸣潮并进入大世界")
        return 2
    print(f"已找到窗口：{window.title or window.class_name} ({window.hwnd})")

    templates = TemplateSet(
        TEMPLATE_DIR,
        hcenter=HCENTER_FEATURES,
        vcenter=VCENTER_FEATURES,
    )
    capture = WindowCapture(window)
    game_input = GameInput(window.hwnd, window.client_rect, use_foreground=args.foreground)

    if args.dry_run:
        frame = capture.grab()
        if frame is None:
            print("截图失败")
            return 3
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output), frame)
        print(f"截图已保存：{output} 尺寸={frame.shape[1]}x{frame.shape[0]}")
        print(f"模板数量：{len(templates.names())}，乐园模板：{sum(1 for n in templates.names() if n.startswith('garden_'))}")
        print("窗口接近全黑：", capture.last_black_frame)
        capture.close()
        return 0

    ocr = None
    if not args.no_ocr:
        try:
            from garden_pilot.ocr import TextRecognizer

            print("初始化 OCR…")
            ocr = TextRecognizer()
        except Exception as exc:
            print(f"OCR 初始化失败（将跳过文本判定）：{exc}")

    runner = GardenRunner(templates, capture, game_input, ocr=ocr)
    try:
        runner.run()
    except KeyboardInterrupt:
        print("已停止")
    except Exception as exc:
        frame = runner.frame
        if frame is not None:
            error_path = LOG_DIR / "garden_error.png"
            error_path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(error_path), frame)
            print(f"已保存出错截图：{error_path}")
        print(f"运行失败：{exc}")
        return 1
    finally:
        capture.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
