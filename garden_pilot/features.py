"""Template geometry loaded from ok-ww assets/templates crops."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

_TEMPLATE_RE = re.compile(
    r"^(?P<name>.+)_(?P<iw>\d+)x(?P<ih>\d+)_(?P<x>\d+)_(?P<y>\d+)\.png$"
)


@dataclass(frozen=True)
class TemplateMeta:
    name: str
    filename: str
    x: int
    y: int
    width: int
    height: int


@dataclass
class Template:
    name: str
    x: int
    y: int
    image: np.ndarray

    @property
    def width(self) -> int:
        return int(self.image.shape[1])

    @property
    def height(self) -> int:
        return int(self.image.shape[0])


def _anchor(value: int, source_size: int, target_size: int, scale: float, center: bool) -> int:
    if center:
        return round(target_size * 0.5 + (value - source_size * 0.5) * scale)
    if value > source_size / 2:
        return target_size - round((source_size - value) * scale)
    return round(value * scale)


class TemplateSet:
    """Lazily loaded template crops described by their PNG file names.

    File names look like garden_get_skip_1920x1080_997_835.png: the
    feature name followed by the screenshot size and the crop origin.
    """

    def __init__(
        self,
        folder: str | Path,
        screen: tuple[int, int] = (1920, 1080),
        hcenter: tuple[str, ...] = (),
        vcenter: tuple[str, ...] = (),
    ) -> None:
        self.folder = Path(folder)
        self.screen_width, self.screen_height = screen
        self.hcenter = set(hcenter)
        self.vcenter = set(vcenter)
        self._meta: dict[str, TemplateMeta] = {}
        self._cache: dict[str, Template] = {}
        self._scan()

    def _scan(self) -> None:
        if not self.folder.is_dir():
            raise FileNotFoundError(f"template folder not found: {self.folder}")
        for path in sorted(self.folder.glob("*.png")):
            match = _TEMPLATE_RE.match(path.name)
            if not match:
                continue
            image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError(f"cannot read template: {path}")
            name = match.group("name")
            image_width = int(match.group("iw"))
            image_height = int(match.group("ih"))
            x = int(match.group("x"))
            y = int(match.group("y"))
            scale = min(self.screen_width / image_width, self.screen_height / image_height)
            width = max(1, round(image.shape[1] * scale))
            height = max(1, round(image.shape[0] * scale))
            x = _anchor(x, image_width, self.screen_width, scale, "hcenter" in name or name in self.hcenter)
            y = _anchor(y, image_height, self.screen_height, scale, "vcenter" in name or name in self.vcenter)
            self._meta[name] = TemplateMeta(name, path.name, x, y, width, height)

    def names(self) -> list[str]:
        return sorted(self._meta)

    def get(self, name: str) -> Template:
        cached = self._cache.get(name)
        if cached is not None:
            return cached
        meta = self._meta.get(name)
        if meta is None:
            raise KeyError(f"template not found: {name}")
        path = self.folder / meta.filename
        image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"cannot read template: {path}")
        if (image.shape[1], image.shape[0]) != (meta.width, meta.height):
            image = cv2.resize(image, (meta.width, meta.height), interpolation=cv2.INTER_AREA)
        template = Template(meta.name, meta.x, meta.y, image)
        self._cache[name] = template
        return template

    def meta(self, name: str) -> TemplateMeta:
        try:
            return self._meta[name]
        except KeyError as exc:
            raise KeyError(f"template not found: {name}") from exc

    def __contains__(self, name: object) -> bool:
        return name in self._meta
