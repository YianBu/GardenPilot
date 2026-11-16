"""Desktop UI for the standalone weekly garden runner."""

from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QSize, Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

GARDEN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(GARDEN_DIR))

import cv2

from garden_pilot.capture import WindowCapture
from garden_pilot.features import TemplateSet
from garden_pilot.input import GameInput
from garden_pilot.paths import ICON_PATH, LOG_DIR, TEMPLATE_DIR
from garden_pilot.runner import GardenRunner, StopRequested
from garden_pilot.window import enable_dpi_awareness, find_game_window

from run_garden import HCENTER_FEATURES, VCENTER_FEATURES

STYLE = """
QMainWindow, QWidget { background: #1e2228; color: #e6e8eb; }
QGroupBox {
    border: 1px solid #343a42; border-radius: 8px; margin-top: 10px; padding-top: 8px;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #9aa4b2; }
QPushButton {
    background: #2d333b; border: 1px solid #3d4550; border-radius: 6px;
    padding: 8px 16px; color: #e6e8eb;
}
QPushButton:hover { background: #363d47; }
QPushButton:disabled { color: #6b7280; background: #262b32; }
QPushButton#start { background: #1f6f4a; border-color: #2b8a5e; font-weight: 600; }
QPushButton#start:hover { background: #25855a; }
QPushButton#stop { background: #7a2f2f; border-color: #994040; font-weight: 600; }
QPushButton#stop:hover { background: #8f3838; }
QPlainTextEdit {
    background: #14171c; border: 1px solid #343a42; border-radius: 6px;
    color: #c7d0da; selection-background-color: #2f6b4f;
}
QCheckBox { spacing: 8px; }
QLabel#title { font-size: 20px; font-weight: 700; }
QLabel#hint { color: #8b94a1; }
QLabel#status { color: #8fd3ac; font-weight: 600; }
"""


class Worker(QObject):
    log = Signal(str)
    status = Signal(str)
    preview = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, use_ocr: bool, foreground: bool) -> None:
        super().__init__()
        self.use_ocr = use_ocr
        self.foreground = foreground
        self.runner: GardenRunner | None = None
        self.capture: WindowCapture | None = None

    def stop(self) -> None:
        if self.runner is not None:
            self.runner.stop_requested = True

    @Slot()
    def run(self) -> None:
        try:
            window = find_game_window()
            if window is None:
                raise RuntimeError("没有找到鸣潮窗口，请先启动游戏")
            self.status.emit("读取模板")
            templates = TemplateSet(
                TEMPLATE_DIR,
                hcenter=HCENTER_FEATURES,
                vcenter=VCENTER_FEATURES,
            )
            self.capture = WindowCapture(window)
            game_input = GameInput(window.hwnd, window.client_rect, use_foreground=self.foreground)
            ocr = None
            if self.use_ocr:
                self.status.emit("初始化 OCR")
                from garden_pilot.ocr import TextRecognizer

                ocr = TextRecognizer()
            self.runner = GardenRunner(
                templates,
                self.capture,
                game_input,
                ocr=ocr,
                on_log=self.log.emit,
                on_frame=self.preview.emit,
                on_status=self.status.emit,
            )
            self.runner.run()
        except StopRequested:
            self.log.emit("已停止")
            self.status.emit("已停止")
        except Exception as exc:  # noqa: BLE001 - surfaced in the UI
            self.log.emit("错误：" + str(exc))
            traceback.print_exc()
            self.failed.emit(str(exc))
        finally:
            if self.capture is not None:
                self.capture.close()
            self.finished.emit()


class GardenWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GardenPilot · 自动周常乐园")
        self.resize(1120, 720)
        icon_path = ICON_PATH
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.thread: QThread | None = None
        self.worker: Worker | None = None
        self.last_frame: np.ndarray | None = None
        self._build_ui()
        self.refresh_window_label()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("GardenPilot")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch(1)
        self.window_label = QLabel("游戏窗口：检测中…")
        self.window_label.setObjectName("hint")
        header.addWidget(self.window_label)
        refresh = QPushButton("刷新窗口")
        refresh.clicked.connect(self.refresh_window_label)
        header.addWidget(refresh)
        layout.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(14)

        preview_panel = QVBoxLayout()
        preview_frame = QFrame()
        preview_frame.setStyleSheet("QFrame { background: #0d0f12; border: 1px solid #343a42; border-radius: 8px; }")
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        self.preview = QLabel("等待画面…")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(QSize(640, 360))
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        preview_layout.addWidget(self.preview)
        preview_panel.addWidget(preview_frame, 1)
        self.status_label = QLabel("空闲")
        self.status_label.setObjectName("status")
        preview_panel.addWidget(self.status_label)
        hint = QLabel("截图来自游戏窗口，被遮挡时也能预览；请勿最小化游戏窗口。")
        hint.setObjectName("hint")
        preview_panel.addWidget(hint)
        body.addLayout(preview_panel, 3)

        side = QVBoxLayout()
        side.setSpacing(10)

        options = QGroupBox("选项")
        options_layout = QVBoxLayout(options)
        self.ocr_check = QCheckBox("启用 OCR 进度判断")
        self.ocr_check.setChecked(True)
        self.foreground_check = QCheckBox("前台点击（默认后台点击）")
        options_layout.addWidget(self.ocr_check)
        options_layout.addWidget(self.foreground_check)
        side.addWidget(options)

        buttons = QGroupBox("控制")
        buttons_layout = QVBoxLayout(buttons)
        self.start_button = QPushButton("开始运行")
        self.start_button.setObjectName("start")
        self.start_button.setMinimumHeight(42)
        self.start_button.clicked.connect(self.start)
        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("stop")
        self.stop_button.setMinimumHeight(36)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)
        self.snap_button = QPushButton("截图测试")
        self.snap_button.clicked.connect(self.snapshot)
        buttons_layout.addWidget(self.start_button)
        buttons_layout.addWidget(self.stop_button)
        buttons_layout.addWidget(self.snap_button)
        side.addWidget(buttons)

        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout(log_group)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setMinimumHeight(220)
        log_layout.addWidget(self.log_view)
        side.addWidget(log_group, 1)

        body.addLayout(side, 2)
        layout.addLayout(body, 1)

    # ------------------------------------------------------------- ui helpers
    def refresh_window_label(self) -> None:
        window = find_game_window()
        if window is None:
            self.window_label.setText("游戏窗口：未找到")
            return
        width, height = window.client_rect()
        self.window_label.setText(f"游戏窗口：{width}x{height}  hwnd={window.hwnd}")

    def append_log(self, message: str) -> None:
        self.log_view.appendPlainText(time.strftime("%H:%M:%S ") + message)

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def show_frame(self, frame: np.ndarray) -> None:
        self.last_frame = frame
        rgb = np.ascontiguousarray(frame[:, :, ::-1])
        height, width = rgb.shape[:2]
        image = QImage(rgb.data, width, height, 3 * width, QImage.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(image)
        target = self.preview.size()
        self.preview.setPixmap(
            pixmap.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    # ---------------------------------------------------------------- actions
    def snapshot(self) -> None:
        window = find_game_window()
        if window is None:
            QMessageBox.warning(self, "自动周常乐园", "没有找到游戏窗口，请先启动鸣潮")
            return
        capture = WindowCapture(window)
        try:
            frame = capture.grab()
        finally:
            capture.close()
        if frame is None:
            QMessageBox.warning(self, "自动周常乐园", "截图失败")
            return
        self.show_frame(frame)
        output = LOG_DIR / "garden_frame.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output), frame)
        self.append_log(f"已保存截图 {output}")
        if capture.last_black_frame:
            self.append_log("警告：截图接近全黑，游戏窗口可能处于最小化状态")

    def start(self) -> None:
        if find_game_window() is None:
            QMessageBox.warning(self, "自动周常乐园", "没有找到鸣潮窗口，请先启动游戏并进入大世界")
            return
        self.thread = QThread(self)
        self.worker = Worker(self.ocr_check.isChecked(), self.foreground_check.isChecked())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.append_log)
        self.worker.status.connect(self.set_status)
        self.worker.preview.connect(self.show_frame)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(self.on_finished)
        self.worker.finished.connect(self.thread.quit)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.snap_button.setEnabled(False)
        self.append_log("开始运行")

    def stop(self) -> None:
        if self.worker is not None:
            self.stop_button.setEnabled(False)
            self.set_status("正在停止…")
            self.worker.stop()

    def on_failed(self, message: str) -> None:
        self.set_status("运行失败")
        QMessageBox.critical(self, "自动周常乐园", "运行失败：" + message)

    def on_finished(self) -> None:
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.snap_button.setEnabled(True)
        self.thread = None
        self.worker = None

    def closeEvent(self, event) -> None:
        if self.worker is not None:
            self.worker.stop()
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(5000)
        super().closeEvent(event)


def main() -> int:
    if "--selftest" in sys.argv:
        return run_environment_check()
    enable_dpi_awareness()
    app = QApplication(sys.argv)
    font = QFont("Microsoft YaHei UI", 10)
    app.setFont(font)
    app.setStyleSheet(STYLE)
    window = GardenWindow()
    window.show()
    return app.exec()


def run_environment_check() -> int:
    """Write a small readiness report next to the exe and exit."""
    lines: list[str] = []
    try:
        templates = TemplateSet(TEMPLATE_DIR)
        lines.append(f"templates={len(templates.names())}")
        lines.append(f"garden_templates={sum(1 for n in templates.names() if n.startswith('garden_'))}")
        from garden_pilot.ocr import TextRecognizer

        recognizer = TextRecognizer()
        sample = np.full((120, 320, 3), 240, dtype=np.uint8)
        result = recognizer.texts(sample)
        lines.append(f"ocr_ok=True ocr_texts={result}")
        status = 0
    except Exception as exc:  # noqa: BLE001 - reported in the file
        lines.append("error=" + str(exc))
        lines.append(traceback.format_exc())
        status = 1
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / "selftest.txt").write_text("\n".join(lines), encoding="utf-8")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
