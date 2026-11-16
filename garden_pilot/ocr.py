"""Text recognition through the onnxocr package (OpenVINO backend)."""

from __future__ import annotations

import numpy as np


def _collect_texts(node, out: list[str]) -> None:
    if isinstance(node, (list, tuple)):
        if len(node) == 2 and isinstance(node[1], (list, tuple)) and len(node[1]) == 2 and isinstance(node[1][0], str):
            out.append(node[1][0])
            return
        if len(node) == 2 and isinstance(node[0], str):
            out.append(node[0])
            return
        for child in node:
            _collect_texts(child, out)


class TextRecognizer:
    def __init__(self, use_openvino: bool = True, use_npu: bool = False) -> None:
        from onnxocr.onnx_paddleocr import ONNXPaddleOcr

        self._ocr = ONNXPaddleOcr(use_openvino=use_openvino, use_npu=use_npu, use_angle_cls=False)

    def texts(self, image: np.ndarray) -> list[str]:
        if image is None or image.size == 0:
            return []
        try:
            result = self._ocr.ocr(image, det=True, rec=True, cls=False)
        except TypeError:
            result = self._ocr.ocr(image)
        texts: list[str] = []
        _collect_texts(result, texts)
        return texts
