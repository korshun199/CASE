"""Полноэкранный видеоконтур CASE с детекцией YOLOv8 через OpenCV DNN."""

from __future__ import annotations

import base64
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import cv2

from app.configuration import ConfigError, load_configurations
from vision.VIDEOSCAN.detector import Detection, decode_yolov8


# Корень CASE вычисляется от расположения этого модуля и не зависит от cwd.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
USER_CONFIG_PATH = PROJECT_ROOT / "config" / "user_config.json"
ADMIN_CONFIG_PATH = PROJECT_ROOT / "config" / "admin_conf.json"


class VideoScanWindow(tk.Tk):
    """Показывает поток камеры и безопасно возвращает пользователя в главное меню."""

    def __init__(self, admin_config: dict) -> None:
        """Загружает модель, открывает UVC-камеру и строит закрытый экран приложения."""
        super().__init__()
        self.settings = admin_config["videoscan"]
        self.source_settings = self.settings["video_source"]
        self.capture: cv2.VideoCapture | None = None
        self.network: cv2.dnn_Net | None = None
        self.photo: tk.PhotoImage | None = None
        self.after_id: str | None = None
        self.reconnect_after_id: str | None = None
        self.closed = False

        self.title(self.settings["title"])
        self.configure(background=self.settings["surface_color"], cursor="left_ptr")
        self.attributes("-fullscreen", True)
        self.protocol("WM_DELETE_WINDOW", self.return_to_menu)
        self.build_interface()
        self.open_pipeline()

    def build_interface(self) -> None:
        """Создаёт только разрешённые элементы VIDEOSCAN без доступа к рабочему столу."""
        self.header = tk.Frame(self, background=self.settings["surface_color"], height=80)
        self.header.pack(fill="x", padx=28, pady=(18, 8))
        self.header.pack_propagate(False)
        tk.Label(
            self.header,
            text=self.settings["title"],
            foreground="#FFFFFF",
            background=self.settings["surface_color"],
            font=("DejaVu Sans", 24, "bold"),
            anchor="w",
        ).pack(side="left", fill="y")
        tk.Label(
            self.header,
            text=self.settings["subtitle"],
            foreground="#9FB3C8",
            background=self.settings["surface_color"],
            font=("DejaVu Sans", 14),
            anchor="e",
        ).pack(side="right", fill="y")

        self.video_label = tk.Label(self, background="#000000")
        self.video_label.pack(fill="both", expand=True, padx=28, pady=8)
        self.info = tk.StringVar(value="Подготовка видеопотока…")
        tk.Label(
            self,
            textvariable=self.info,
            foreground="#FFFFFF",
            background=self.settings["surface_color"],
            font=("DejaVu Sans", 14),
        ).pack(fill="x", padx=28, pady=6)
        tk.Button(
            self,
            text="Главное меню",
            command=self.return_to_menu,
            foreground="#FFFFFF",
            background="#176B87",
            activebackground="#2385A5",
            font=("DejaVu Sans", 18, "bold"),
            relief="flat",
            padx=26,
            pady=10,
        ).pack(pady=(4, 20))

    def open_pipeline(self) -> None:
        """Проверяет модель и камеру; при ошибке оставляет безопасную кнопку возврата."""
        try:
            model_path = Path(self.settings["model_path"])
            if not model_path.is_file():
                raise FileNotFoundError(f"модель не найдена: {model_path}")
            self.network = cv2.dnn.readNetFromONNX(str(model_path))
            self.network.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self.network.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

            device = self.source_settings["device"]
            self.info.set(f"Модель загружена • ожидание камеры {device}")
            self.reconnect_camera()
        except (OSError, cv2.error, ValueError) as error:
            self.info.set(f"Ошибка VIDEOSCAN: {error}")

    def schedule_camera_reconnect(self) -> None:
        """Планирует одну повторную попытку открыть UVC-камеру."""
        if not self.closed and self.reconnect_after_id is None:
            self.reconnect_after_id = self.after(
                self.settings["camera_reconnect_interval_ms"], self.reconnect_camera
            )

    def reconnect_camera(self) -> None:
        """Открывает стабильный путь камеры и повторяет попытку после её переподключения."""
        self.reconnect_after_id = None
        if self.closed:
            return
        device = self.source_settings["device"]
        try:
            capture = cv2.VideoCapture(device, cv2.CAP_V4L2)
            if not capture.isOpened():
                capture.release()
                self.capture = None
                self.info.set(f"Ожидание USB-камеры: {device}")
                self.schedule_camera_reconnect()
                return
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.source_settings["width"])
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.source_settings["height"])
            capture.set(cv2.CAP_PROP_FPS, self.source_settings["fps"])
            self.capture = capture
            self.info.set(f"Камера подключена • {device} • YOLOv8 CPU")
            self.schedule_frame()
        except cv2.error as error:
            self.capture = None
            self.info.set(f"Ошибка открытия USB-камеры: {error}")
            self.schedule_camera_reconnect()

    def schedule_frame(self) -> None:
        """Запрашивает следующий кадр через интервал из административной конфигурации."""
        if not self.closed:
            self.after_id = self.after(self.settings["frame_interval_ms"], self.process_frame)

    def process_frame(self) -> None:
        """Читает кадр, выполняет детекцию и обновляет изображение на экране."""
        if self.closed or self.network is None:
            return
        if self.capture is None:
            self.schedule_camera_reconnect()
            return
        ok, frame = self.capture.read()
        if not ok or frame is None:
            self.info.set("Ошибка чтения кадра USB-камеры")
            self.capture.release()
            self.capture = None
            self.schedule_camera_reconnect()
            return

        try:
            input_width = self.settings["input_width"]
            input_height = self.settings["input_height"]
            blob = cv2.dnn.blobFromImage(
                cv2.resize(frame, (input_width, input_height)),
                scalefactor=1 / 255.0,
                size=(input_width, input_height),
                swapRB=True,
                crop=False,
            )
            self.network.setInput(blob)
            output = self.network.forward()
            detections = decode_yolov8(
                output,
                self.settings["class_names"],
                self.settings["confidence_threshold"],
                self.settings["nms_threshold"],
            )
            draw_frame = self.draw_detections(frame, detections)
            encoded_ok, encoded = cv2.imencode(".png", cv2.cvtColor(draw_frame, cv2.COLOR_BGR2RGB))
            if not encoded_ok:
                raise OSError("не удалось подготовить кадр для экрана")
            self.photo = tk.PhotoImage(data=base64.b64encode(encoded.tobytes()), format="png")
            self.video_label.configure(image=self.photo)
            self.info.set(f"Камера {self.source_settings['device']} • обнаружено объектов: {len(detections)}")
        except (OSError, cv2.error, ValueError) as error:
            self.info.set(f"Ошибка обработки кадра: {error}")
        self.schedule_frame()

    def draw_detections(self, frame, detections: list[Detection]):
        """Рисует рамки модели, переводя координаты 320x320 в размеры исходного кадра."""
        height, width = frame.shape[:2]
        scale_x = width / self.settings["input_width"]
        scale_y = height / self.settings["input_height"]
        overlay_color = self.hex_to_bgr(self.settings["overlay_color"])
        text_color = self.hex_to_bgr(self.settings["overlay_text_color"])
        for detection in detections:
            x = max(0, int(detection.x * scale_x))
            y = max(0, int(detection.y * scale_y))
            right = min(width - 1, int((detection.x + detection.width) * scale_x))
            bottom = min(height - 1, int((detection.y + detection.height) * scale_y))
            cv2.rectangle(frame, (x, y), (right, bottom), overlay_color, 2)
            caption = f"{detection.class_name}: {detection.confidence:.0%}"
            cv2.putText(frame, caption, (x, max(24, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, text_color, 2)
        return frame

    @staticmethod
    def hex_to_bgr(value: str) -> tuple[int, int, int]:
        """Преобразует административный цвет #RRGGBB в формат BGR OpenCV."""
        if len(value) != 7 or not value.startswith("#"):
            raise ValueError(f"некорректный цвет OpenCV: {value}")
        red = int(value[1:3], 16)
        green = int(value[3:5], 16)
        blue = int(value[5:7], 16)
        return blue, green, red

    def return_to_menu(self) -> None:
        """Останавливает камеру и завершает дочернее окно, чтобы оболочка показала меню."""
        if self.closed:
            return
        self.closed = True
        if self.after_id is not None:
            self.after_cancel(self.after_id)
        if self.reconnect_after_id is not None:
            self.after_cancel(self.reconnect_after_id)
        if self.capture is not None:
            self.capture.release()
        self.destroy()


def main() -> int:
    """Загружает конфигурацию и запускает VIDEOSCAN в отдельном kiosk-окне."""
    try:
        _, admin_config = load_configurations(USER_CONFIG_PATH, ADMIN_CONFIG_PATH)
        window = VideoScanWindow(admin_config)
    except (ConfigError, OSError, cv2.error, ValueError) as error:
        print(f"[ERROR] VIDEOSCAN: {error}", file=sys.stderr)
        return 2
    window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
