"""Единая проверка структуры и конфигурации первого прототипа CASE."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Callable

import numpy as np

from app.configuration import ConfigError, load_configurations, validate_admin_config
from vision.VIDEOSCAN.detector import decode_yolov8


PROJECT_ROOT = Path(__file__).resolve().parent
USER_CONFIG_PATH = PROJECT_ROOT / "config" / "user_config.json"
ADMIN_CONFIG_PATH = PROJECT_ROOT / "config" / "admin_conf.json"
MENU_APPLICATION_PATH = PROJECT_ROOT / "app" / "main.py"
STATUS_MODULE_PATH = PROJECT_ROOT / "app" / "system_status.py"
VIDEOSCAN_DIRECTORY = PROJECT_ROOT / "vision" / "VIDEOSCAN"
VIDEOSCAN_MODULE_PATH = VIDEOSCAN_DIRECTORY / "__main__.py"
VIDEOSCAN_REQUIREMENTS_PATH = VIDEOSCAN_DIRECTORY / "requirements-dev.txt"
QEMU_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "qemu_aarch64.sh"
BOOTSTRAP_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "bootstrap_orangepi5_access.sh"


def check_required_paths() -> None:
    """Проверяет постоянные файлы, без которых прототип не запускается."""
    required_paths = (USER_CONFIG_PATH, ADMIN_CONFIG_PATH, MENU_APPLICATION_PATH, STATUS_MODULE_PATH)
    missing_paths = [str(path.relative_to(PROJECT_ROOT)) for path in required_paths if not path.is_file()]
    if missing_paths:
        raise RuntimeError("Не найдены обязательные файлы: " + ", ".join(missing_paths))
    videoscan_files = (
        VIDEOSCAN_DIRECTORY / "__init__.py",
        VIDEOSCAN_MODULE_PATH,
        VIDEOSCAN_DIRECTORY / "README.md",
        VIDEOSCAN_REQUIREMENTS_PATH,
        QEMU_SCRIPT_PATH,
        BOOTSTRAP_SCRIPT_PATH,
    )
    missing_videoscan = [str(path.relative_to(PROJECT_ROOT)) for path in videoscan_files if not path.is_file()]
    if missing_videoscan:
        raise RuntimeError("Не найдены файлы VIDEOSCAN: " + ", ".join(missing_videoscan))


def check_configurations() -> None:
    """Проверяет обе конфигурации общей строгой схемой приложения."""
    load_configurations(USER_CONFIG_PATH, ADMIN_CONFIG_PATH)


def check_videoscan_configuration() -> None:
    """Проверяет, что административные параметры VIDEOSCAN присутствуют и валидны."""
    _, admin_config = load_configurations(USER_CONFIG_PATH, ADMIN_CONFIG_PATH)
    videoscan = admin_config["videoscan"]
    if videoscan["inference_backend"] != "opencv_dnn" or videoscan["model_format"] != "onnx":
        raise RuntimeError("Для VIDEOSCAN ожидается OpenCV DNN с моделью ONNX")
    if not videoscan["model_path"].endswith("fpv_drone_custom_320.onnx"):
        raise RuntimeError("Первой моделью VIDEOSCAN должна быть проверенная FPV-модель 320x320")
    if videoscan["class_names"] != ["quadcopter"]:
        raise RuntimeError("Список классов должен соответствовать выбранной FPV-модели")
    device = videoscan["video_source"]["device"]
    if not device.endswith("usb-046d_Brio_90_2613ZBY23218-video-index0"):
        raise RuntimeError("Для Orange Pi 5 нужен стабильный путь к USB-камере Brio")
    if videoscan["camera_reconnect_interval_ms"] < 500:
        raise RuntimeError("Повторное подключение камеры настроено слишком часто")
    recognition_app = next(
        app for app in admin_config["applications"] if app["id"] == "video_recognition"
    )
    if recognition_app["launch"]["argv"][0] != "/opt/case/videoscan-venv/bin/python":
        raise RuntimeError("Распознавание должно запускаться в изолированной среде OpenCV")


def check_yolov8_decoder() -> None:
    """Подтверждает выбор класса, порога и подавление дублирующих рамок YOLOv8."""
    output = np.array([[
        [100.0, 101.0, 200.0], [100.0, 101.0, 200.0], [40.0, 40.0, 20.0], [40.0, 40.0, 20.0], [0.9, 0.8, 0.1]
    ]])
    detections = decode_yolov8(output, ["quadcopter"], 0.25, 0.45)
    if len(detections) != 1 or detections[0].class_name != "quadcopter":
        raise RuntimeError("Декодер YOLOv8 неверно обработал кандидаты")


def check_invalid_admin_configuration_is_rejected() -> None:
    """Подтверждает, что недопустимый размер текста блокирует запуск."""
    _, admin_config = load_configurations(USER_CONFIG_PATH, ADMIN_CONFIG_PATH)
    invalid_config = deepcopy(admin_config)
    invalid_config["applications"][0]["button"]["font_size"] = 0
    try:
        validate_admin_config(invalid_config)
    except ConfigError:
        return
    raise RuntimeError("Недопустимый размер текста кнопки не был отклонён")


def check_invalid_launch_command_is_rejected() -> None:
    """Подтверждает, что команда запуска обязана задаваться абсолютным argv."""
    _, admin_config = load_configurations(USER_CONFIG_PATH, ADMIN_CONFIG_PATH)
    invalid_config = deepcopy(admin_config)
    invalid_config["applications"][0]["launch"]["argv"] = ["sh", "-c", "id"]
    try:
        validate_admin_config(invalid_config)
    except ConfigError:
        return
    raise RuntimeError("Команда запуска без абсолютного пути не была отклонена")


def check_overlapping_buttons_are_rejected() -> None:
    """Подтверждает, что профили монитора не размещают кнопки друг поверх друга."""
    _, admin_config = load_configurations(USER_CONFIG_PATH, ADMIN_CONFIG_PATH)
    invalid_config = deepcopy(admin_config)
    positions = invalid_config["display"]["profiles"]["case_17_full_hd"]["button_positions"]
    positions["radio_scan"] = deepcopy(positions["video_recognition"])
    try:
        validate_admin_config(invalid_config)
    except ConfigError:
        return
    raise RuntimeError("Перекрывающиеся кнопки не были отклонены")


def check_menu_module() -> None:
    """Проверяет, что главный модуль оболочки можно разобрать без запуска окна."""
    source_code = MENU_APPLICATION_PATH.read_text(encoding="utf-8")
    compile(source_code, str(MENU_APPLICATION_PATH), "exec")


def check_system_status_module() -> None:
    """Проверяет, что экран состояния компилируется без запуска графической сессии."""
    source_code = STATUS_MODULE_PATH.read_text(encoding="utf-8")
    compile(source_code, str(STATUS_MODULE_PATH), "exec")


def check_videoscan_module() -> None:
    """Проверяет синтаксис видеоконтурa без открытия камеры."""
    source_code = VIDEOSCAN_MODULE_PATH.read_text(encoding="utf-8")
    compile(source_code, str(VIDEOSCAN_MODULE_PATH), "exec")


def run_check(name: str, check: Callable[[], None]) -> bool:
    """Запускает одну проверку и печатает единый результат для владельца."""
    try:
        check()
    except (ConfigError, OSError, RuntimeError, SyntaxError) as error:
        print(f"[ERROR] {name}: {error}")
        return False
    print(f"[OK] {name}")
    return True


def main() -> int:
    """Выполняет полный набор безопасных локальных проверок прототипа."""
    checks = (
        ("Наличие обязательных файлов", check_required_paths),
        ("Конфигурация пользователя и администратора", check_configurations),
        ("Конфигурация системы VIDEOSCAN", check_videoscan_configuration),
        ("Декодирование результата YOLOv8", check_yolov8_decoder),
        ("Отклонение недопустимого размера текста кнопки", check_invalid_admin_configuration_is_rejected),
        ("Отклонение небезопасного формата команды запуска", check_invalid_launch_command_is_rejected),
        ("Отклонение перекрывающихся кнопок", check_overlapping_buttons_are_rejected),
        ("Синтаксис главного меню", check_menu_module),
        ("Синтаксис экрана состояния", check_system_status_module),
        ("Синтаксис приложения VIDEOSCAN", check_videoscan_module),
    )
    results = [run_check(name, check) for name, check in checks]
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
