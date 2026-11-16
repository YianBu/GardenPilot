"""Weekly garden state machine, ported from ok-ww src/task/GardenTask.py."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

import cv2
import numpy as np

from .capture import WindowCapture
from .features import TemplateSet
from .input import GameInput
from .vision import Box, Matcher

LOGGER = logging.getLogger("okww_garden")

POINTS_PATTERN = re.compile("6000")

PRIORITY_FEATURES = ("garden_get_skip", "garden_not_interested_confirm")
SKIPPED_FEATURES = ("garden_get_confirm_gray", "garden_not_interested_confirm")


class StopRequested(Exception):
    """Raised when the user stops the runner from the UI."""


def _sort_boxes(boxes: list[Box]) -> list[Box]:
    return sorted(boxes, key=lambda box: (box.y, box.x))


class GardenRunner:
    def __init__(
        self,
        templates: TemplateSet,
        capture: WindowCapture,
        game_input: GameInput,
        ocr=None,
        screen: tuple[int, int] = (1920, 1080),
        debug_dir: str | Path | None = None,
        on_log=None,
        on_frame=None,
        on_status=None,
        preview_interval: float = 0.3,
    ) -> None:
        self.templates = templates
        self.capture = capture
        self.input = game_input
        self.ocr = ocr
        self.screen_width, self.screen_height = screen
        self.matcher = Matcher(templates)
        self.debug_dir = Path(debug_dir) if debug_dir else None
        self.frame: np.ndarray | None = None
        self.last_boxes: list[Box] = []
        self.stop_requested = False
        self.on_log = on_log
        self.on_frame = on_frame
        self.on_status = on_status
        self.preview_interval = preview_interval
        self._last_preview = 0.0
        self._last_black_warning = 0.0
        self.current_status = ""
        self.garden_features = [name for name in templates.names() if name.startswith("garden_")]

    # ---------------------------------------------------------------- helpers
    def log(self, message: str) -> None:
        LOGGER.info(message)
        if self.on_log is not None:
            self.on_log(message)
        else:
            print(message, flush=True)

    def status(self, message: str) -> None:
        if message == self.current_status:
            return
        self.current_status = message
        if self.on_status is not None:
            self.on_status(message)
        else:
            LOGGER.debug("status: %s", message)

    def check_stop(self) -> None:
        if self.stop_requested:
            raise StopRequested()

    def sleep(self, seconds: float) -> None:
        deadline = time.time() + seconds
        while True:
            self.check_stop()
            remaining = deadline - time.time()
            if remaining <= 0:
                return
            time.sleep(min(0.05, remaining))

    def refresh(self) -> bool:
        frame = self.capture.grab()
        if frame is None:
            self.log("截图失败：游戏窗口可能已关闭或最小化")
            return False
        self.frame = frame
        if self.capture.last_black_frame and time.time() - self._last_black_warning > 10:
            self._last_black_warning = time.time()
            self.log("警告：截图接近全黑，请确认游戏窗口没有被最小化")
        self.emit_preview()
        return True

    def emit_preview(self, force: bool = False) -> None:
        if self.on_frame is None or self.frame is None:
            return
        now = time.time()
        if not force and now - self._last_preview < self.preview_interval:
            return
        self._last_preview = now
        frame = self.frame.copy()
        for box in self.last_boxes[:15]:
            cv2.rectangle(
                frame, (box.x, box.y), (box.x + box.width, box.y + box.height), (0, 200, 255), 2
            )
        self.on_frame(frame)

    def frame_or_refresh(self) -> np.ndarray | None:
        if self.frame is None:
            self.refresh()
        return self.frame

    def find_one(self, name: str, **kwargs) -> Box | None:
        frame = self.frame_or_refresh()
        result = self.matcher.find(name, frame, limit=1, **kwargs)
        box = result if isinstance(result, Box) else None
        if box is not None:
            self.last_boxes = [box]
        return box

    def find_feature(self, name: str, **kwargs) -> list[Box]:
        frame = self.frame_or_refresh()
        result = self.matcher.find(name, frame, limit=0, **kwargs)
        if isinstance(result, Box):
            boxes = [result]
        else:
            boxes = _sort_boxes(result or [])
        if boxes:
            self.last_boxes = boxes
        return boxes

    def box_by_name(self, name: str) -> Box:
        meta = self.templates.meta(name)
        return Box(meta.x, meta.y, meta.width, meta.height, 1.0, name)

    def click_box(self, box: Box | None, after_sleep: float = 0.0) -> None:
        if box is None:
            return
        x, y = box.center
        self.input.click_px(x, y, down_time=0.2, after_sleep=after_sleep)

    def click_norm(self, x_ratio: float, y_ratio: float, after_sleep: float = 0.0) -> None:
        self.input.click_norm(x_ratio, y_ratio, down_time=0.2, after_sleep=after_sleep)

    def wait_until(self, predicate, timeout: float, interval: float = 0.3) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.check_stop()
            if predicate():
                return True
            self.sleep(interval)
        return False

    def wait_feature(self, name: str, time_out: float = 3.0, settle_time: float = 0.0, **kwargs) -> Box | None:
        found: Box | None = None

        def check() -> bool:
            nonlocal found
            self.refresh()
            found = self.find_one(name, **kwargs)
            return found is not None

        if self.wait_until(check, time_out, interval=max(0.2, min(1.0, settle_time or 0.3))):
            return found
        return None

    def ocr_texts(self, region: tuple[float, float, float, float] | None = None) -> list[str] | None:
        if self.ocr is None:
            return None
        self.refresh()
        frame = self.frame
        if frame is None:
            return None
        if region is not None:
            height, width = frame.shape[:2]
            frame = frame[
                round(region[1] * height) : round(region[3] * height),
                round(region[0] * width) : round(region[2] * width),
            ]
        try:
            return self.ocr.texts(frame)
        except Exception as exc:
            self.log(f"OCR 失败：{exc}")
            return None

    # ------------------------------------------------------------- game state
    def in_team(self) -> bool:
        exists = 0
        for name in ("char_1_text", "char_2_text", "char_3_text"):
            if name in self.templates and self.find_one(name) is not None:
                exists += 1
        return exists in (1, 2)

    def ensure_main(self, time_out: float = 30.0) -> None:
        self.status("等待进入游戏大世界")
        self.log("等待进入游戏大世界…")

        def ready() -> bool:
            self.refresh()
            return self.in_team()

        if self.wait_until(ready, time_out, interval=0.5):
            self.sleep(0.5)
            return
        self.check_stop()
        raise RuntimeError("请先进入游戏大世界（队伍界面）后再运行本脚本")

    def wait_book(self, feature: str = "gray_book_all_monsters", time_out: float = 3.0) -> Box | None:
        return self.wait_feature(feature, time_out=time_out)

    def open_book(self, feature: str = "gray_book_all_monsters") -> Box:
        self.ensure_main()
        self.status("打开索拉指南")
        self.log("按 F2 打开索拉指南")
        self.input.send_key("f2")
        self.sleep(4)
        self.refresh()
        if self.in_team():
            self.log("F2 未生效，改用 Alt+点击 打开指南")
            self.input.alt_click_norm(0.77, 0.05)
            self.sleep(4)
        gray_book = self.wait_book(feature, time_out=3)
        if gray_book is None:
            raise RuntimeError("找不到索拉指南入口，请确认 F2 是打开指南的快捷键")
        self.sleep(2)
        self.click_box(gray_book, after_sleep=1.5)
        return gray_book

    # ---------------------------------------------------------------- garden
    def open_garden_weekly_page(self) -> None:
        self.status("进入周常乐园页面")
        self.open_book("gray_book_quest")
        self.click_norm(0.343, 0.129, after_sleep=1)
        self.click_norm(0.927, 0.893, after_sleep=3)
        self.click_norm(0.927, 0.893, after_sleep=2)

    def is_weekly_completed(self) -> bool:
        texts = self.ocr_texts((0.102, 0.793, 0.284, 0.956))
        if texts is None:
            self.log("未启用 OCR，跳过每周进度检查")
            return False
        current = " ".join(texts)
        self.log(f"乐园进度文本：{current!r}")
        return bool(POINTS_PATTERN.search(current))

    def is_garden_done(self, texts: list[str]) -> bool:
        return " ".join(texts).count(POINTS_PATTERN.pattern) != 1

    def find_best_garden_feature(self) -> Box | None:
        self.refresh()
        matches: list[Box] = []
        for name in self.garden_features:
            if name in SKIPPED_FEATURES:
                continue
            if name == "garden_not_interested":
                matches.extend(self.find_feature(name, vertical_variance=0.4))
            else:
                matches.extend(self.find_feature(name))
        self.last_boxes = matches
        for name in PRIORITY_FEATURES:
            priority = [box for box in matches if box.name == name]
            if priority:
                return max(priority, key=lambda box: box.confidence)
        return max(matches, key=lambda box: box.confidence, default=None)

    def choose_first_blessing(self) -> None:
        self.status("选择祝福")
        self.click_norm(965 / 1920, 860 / 1080, after_sleep=2)
        self.click_norm(700 / 1920, 666 / 1080, after_sleep=2)
        self.click_norm(1600 / 1920, 900 / 1080, after_sleep=2)

    def run(self) -> None:
        self.ensure_main()
        self.open_garden_weekly_page()
        if self.is_weekly_completed():
            self.status("本周已完成")
            self.log("周常乐园已达上限，无需执行")
            return
        self.status("点击进入乐园")
        self.click_norm(0.246, 0.486, after_sleep=1)
        while True:
            self.check_stop()
            self.sleep(0.1)
            target = self.find_best_garden_feature()
            self.sleep(0.2)
            if target is not None:
                self.status(f"识别到 {target.name}")
                self.log(f"识别到 {target.name} ({target.confidence:.3f})")
                if target.name == "garden_get_skip":
                    self.sleep(1)
                    gold = self.find_one("garden_get_gold", horizontal_variance=0.9)
                    if gold is not None:
                        self.click_box(gold, after_sleep=1)
                    else:
                        purple = self.find_one("garden_get_purple", horizontal_variance=0.9)
                        if purple is not None:
                            self.click_box(purple, after_sleep=1)
                        else:
                            self.click_norm(0.5, 0.2, after_sleep=1)
                    self.click_box(self.box_by_name("garden_get_confirm_gray"), after_sleep=1)
                    continue
                if target.name == "garden_not_interested":
                    not_interested = self.find_feature("garden_not_interested", vertical_variance=0.4)
                    if not_interested:
                        self.click_box(not_interested[-1], after_sleep=1)
                    self.click_box(self.box_by_name("garden_not_interested_confirm"), after_sleep=1)
                    continue
                if target.name == "garden_start_game":
                    self.choose_first_blessing()
                self.click_box(target, after_sleep=1)
                continue

            restart = self.find_one("a_garden_restart")
            back = self.find_one("a_garden_back")
            if restart is not None and back is not None:
                self.status("结算页面")
                self.sleep(2)
                texts = self.ocr_texts((0.373, 0.346, 0.859, 0.615))
                self.log(f"结算界面文本：{texts}")
                if texts is None or self.is_garden_done(texts):
                    self.click_box(back, after_sleep=1)
                    if self.wait_feature("garden_start_game", time_out=5, settle_time=1):
                        self.input.back()
                        self.sleep(1)
                    if self.wait_book("gray_book_quest", time_out=30):
                        self.click_norm(0.927, 0.893, after_sleep=2)
                        self.click_norm(0.927, 0.893, after_sleep=1)
                    break
                self.click_box(restart, after_sleep=1)
            self.sleep(0.2)
        self.status("已完成")
        self.log("乐园任务结束")
