"""Offline checks that do not require the game to be running."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

GARDEN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(GARDEN_DIR))

from garden_pilot.features import TemplateSet
from garden_pilot.paths import TEMPLATE_DIR
from garden_pilot.runner import GardenRunner
from garden_pilot.vision import Matcher
from garden_pilot.window import find_game_window


def check_templates() -> TemplateSet:
    templates = TemplateSet(TEMPLATE_DIR)
    garden = [name for name in templates.names() if name.startswith("garden_")]
    print(f"模板总数 {len(templates.names())}，乐园模板 {len(garden)}")
    assert len(templates.names()) >= 20, "template folder looks empty"
    assert "garden_get_skip" in templates, "garden templates missing"
    return templates


def check_matching(templates: TemplateSet) -> None:
    matcher = Matcher(templates)
    template = templates.get("garden_get_skip")
    frame = np.zeros((1080, 1920, 3), np.uint8)
    frame[template.y : template.y + template.height, template.x : template.x + template.width] = template.image
    box = matcher.find("garden_get_skip", frame)
    assert box is not None and box.confidence > 0.99
    assert (box.x, box.y) == (template.x, template.y)
    print(f"匹配通过：{box}")

    widened = matcher.find("garden_get_gold", frame)
    assert widened is None, "unrelated template should not match"

    gold = templates.get("garden_get_gold")
    shifted = np.zeros((1080, 1920, 3), np.uint8)
    shifted[gold.y : gold.y + gold.height, gold.x + 30 : gold.x + 30 + gold.width] = gold.image
    assert matcher.find("garden_get_gold", shifted) is None
    assert matcher.find("garden_get_gold", shifted, horizontal_variance=0.9) is not None
    print("搜索范围放大逻辑通过")

    small = templates.get("garden_not_interested")
    multi = np.zeros((1080, 1920, 3), np.uint8)
    multi[small.y : small.y + small.height, small.x : small.x + small.width] = small.image
    multi[small.y + 80 : small.y + 80 + small.height, small.x : small.x + small.width] = small.image
    boxes = matcher.find("garden_not_interested", multi, vertical_variance=0.4, limit=0)
    assert isinstance(boxes, list) and len(boxes) == 2
    print("多目标匹配通过")


def _paste(frame: np.ndarray, template) -> None:
    frame[template.y : template.y + template.height, template.x : template.x + template.width] = template.image


class FakeCapture:
    def __init__(self, frame: np.ndarray) -> None:
        self.frame = frame
        self.last_black_frame = False

    def grab(self) -> np.ndarray:
        return self.frame

    def close(self) -> None:
        pass


class FakeInput:
    def __init__(self) -> None:
        self.clicks: list[tuple[int, int]] = []

    def client_size(self) -> tuple[int, int]:
        return 1920, 1080

    def click_px(self, x, y, down_time=0.2, after_sleep=0.0) -> None:
        self.clicks.append((x, y))

    def click_norm(self, x_ratio, y_ratio, down_time=0.2, after_sleep=0.0) -> None:
        self.clicks.append((round(x_ratio * 1920), round(y_ratio * 1080)))

    def send_key(self, name, down_time=0.05) -> None:
        pass

    def back(self) -> None:
        pass

    def alt_click_norm(self, x_ratio, y_ratio, after_sleep=0.0) -> None:
        pass


def check_logic(templates: TemplateSet) -> None:
    frame = np.zeros((1080, 1920, 3), np.uint8)
    for name in ("char_1_text", "char_2_text", "garden_get_skip", "garden_get_confirm_gray"):
        _paste(frame, templates.get(name))
    runner = GardenRunner(templates, FakeCapture(frame), FakeInput(), preview_interval=10)
    assert runner.in_team(), "team HUD detection failed"
    best = runner.find_best_garden_feature()
    assert best is not None and best.name == "garden_get_skip", best
    assert runner.is_garden_done(["6000", "6000"]), "double 6000 should mean finished"
    assert not runner.is_garden_done(["6000"]), "single 6000 should mean not finished"
    runner.click_box(best)
    assert runner.input.clicks, "click was not forwarded"
    print("状态机核心逻辑通过")


def check_ocr() -> None:
    from garden_pilot.ocr import TextRecognizer

    image = Image.new("RGB", (900, 200), (20, 20, 20))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 120)
    draw.text((40, 20), "6000", fill=(240, 240, 240), font=font)
    recognizer = TextRecognizer()
    texts = recognizer.texts(np.array(image)[:, :, ::-1])
    print("OCR 结果：", texts)
    assert any("6000" in text for text in texts), "OCR did not read 6000"


def main() -> int:
    templates = check_templates()
    check_matching(templates)
    check_logic(templates)
    if "--ocr" in sys.argv:
        check_ocr()
    window = find_game_window()
    print("游戏窗口：", window.title if window else "未找到")
    print("离线自检通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
