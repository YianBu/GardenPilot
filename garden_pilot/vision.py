"""OpenCV template matching against the game frame."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .features import TemplateSet


@dataclass
class Box:
    x: int
    y: int
    width: int
    height: int
    confidence: float
    name: str

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2


def _non_max_suppression(boxes: list[Box]) -> list[Box]:
    kept: list[Box] = []
    for box in sorted(boxes, key=lambda item: item.confidence, reverse=True):
        overlap = False
        for other in kept:
            if (
                box.x < other.x + other.width
                and other.x < box.x + box.width
                and box.y < other.y + other.height
                and other.y < box.y + box.height
            ):
                overlap = True
                break
        if not overlap:
            kept.append(box)
    return kept


class Matcher:
    def __init__(
        self,
        templates: TemplateSet,
        default_threshold: float = 0.8,
        default_variance: float = 0.002,
    ) -> None:
        self.templates = templates
        self.default_threshold = default_threshold
        self.default_variance = default_variance
        self.screen_width = templates.screen_width
        self.screen_height = templates.screen_height

    def find(
        self,
        name: str,
        frame: np.ndarray,
        threshold: float | None = None,
        horizontal_variance: float | None = None,
        vertical_variance: float | None = None,
        region: tuple[float, float, float, float] | None = None,
        limit: int = 1,
    ) -> Box | list[Box] | None:
        template = self.templates.get(name)
        if frame is None:
            return None if limit == 1 else []
        frame_height, frame_width = frame.shape[:2]
        threshold = self.default_threshold if threshold is None else threshold

        if region is not None:
            x1 = round(region[0] * frame_width)
            y1 = round(region[1] * frame_height)
            x2 = round(region[2] * frame_width)
            y2 = round(region[3] * frame_height)
        else:
            h_variance = self.default_variance if horizontal_variance is None else horizontal_variance
            v_variance = self.default_variance if vertical_variance is None else vertical_variance
            x_offset = self.screen_width * h_variance
            y_offset = self.screen_height * v_variance
            x1 = max(0, round(template.x - x_offset))
            y1 = max(0, round(template.y - y_offset))
            x2 = min(frame_width, round(template.x + template.width + x_offset))
            y2 = min(frame_height, round(template.y + template.height + y_offset))

        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(frame_width, x2), min(frame_height, y2)
        search = frame[y1:y2, x1:x2, :3]
        if search.size == 0:
            return None if limit == 1 else []
        if template.height > search.shape[0] or template.width > search.shape[1]:
            return None if limit == 1 else []

        result = cv2.matchTemplate(search, template.image, cv2.TM_CCOEFF_NORMED)
        np.nan_to_num(result, copy=False, nan=0.0, posinf=0.0, neginf=0.0)

        if limit == 1:
            _, max_value, _, max_location = cv2.minMaxLoc(result)
            if max_value < threshold:
                return None
            return Box(
                x1 + int(max_location[0]),
                y1 + int(max_location[1]),
                template.width,
                template.height,
                float(max_value),
                name,
            )

        ys, xs = np.nonzero(result >= threshold)
        boxes = [
            Box(
                x1 + int(x),
                y1 + int(y),
                template.width,
                template.height,
                float(result[y, x]),
                name,
            )
            for y, x in zip(ys, xs)
        ]
        return _non_max_suppression(boxes)[:limit] if limit > 0 else _non_max_suppression(boxes)
