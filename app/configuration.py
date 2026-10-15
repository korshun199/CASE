"""Загрузка и строгая проверка конфигурации прототипа CASE."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Сообщает о непригодной для безопасного запуска конфигурации."""


def load_json_object(path: Path) -> dict[str, Any]:
    """Читает JSON-объект из файла и превращает ошибку в понятное сообщение."""
    try:
        with path.open("r", encoding="utf-8") as source_file:
            data = json.load(source_file)
    except FileNotFoundError as error:
        raise ConfigError(f"Не найден конфигурационный файл: {path}") from error
    except json.JSONDecodeError as error:
        raise ConfigError(
            f"Некорректный JSON в {path}: строка {error.lineno}, столбец {error.colno}"
        ) from error
    except OSError as error:
        raise ConfigError(f"Не удалось прочитать {path}: {error}") from error

    if not isinstance(data, dict):
        raise ConfigError(f"Корень конфигурации {path} должен быть JSON-объектом")
    return data


def require_mapping(container: dict[str, Any], key: str, location: str) -> dict[str, Any]:
    """Возвращает обязательный JSON-объект или объясняет, где нарушена структура."""
    value = container.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"{location}.{key} должен быть объектом")
    return value


def require_string(container: dict[str, Any], key: str, location: str) -> str:
    """Возвращает непустую строку из конфигурации."""
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{location}.{key} должен быть непустой строкой")
    return value


def require_integer(
    container: dict[str, Any], key: str, location: str, minimum: int, maximum: int
) -> int:
    """Проверяет целое число и его безопасный для интерфейса диапазон."""
    value = container.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ConfigError(f"{location}.{key} должен быть целым числом от {minimum} до {maximum}")
    return value


def require_color(container: dict[str, Any], key: str, location: str) -> str:
    """Проверяет цвет формата #RRGGBB, понятный штатному Tkinter."""
    value = require_string(container, key, location)
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        raise ConfigError(f"{location}.{key} должен иметь формат #RRGGBB")
    return value


def require_number(
    container: dict[str, Any], key: str, location: str, minimum: float, maximum: float
) -> float:
    """Проверяет числовой масштаб или нормированную координату интерфейса."""
    value = container.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{location}.{key} должен быть числом от {minimum} до {maximum}")
    if not minimum <= value <= maximum:
        raise ConfigError(f"{location}.{key} должен быть числом от {minimum} до {maximum}")
    return float(value)


def validate_position(container: dict[str, Any], location: str) -> tuple[float, float, float, float]:
    """Проверяет нормированные координаты прямоугольной области интерфейса."""
    x = require_number(container, "x", location, 0.0, 1.0)
    y = require_number(container, "y", location, 0.0, 1.0)
    width = require_number(container, "width", location, 0.05, 1.0)
    height = require_number(container, "height", location, 0.05, 1.0)
    if x + width > 1.0 or y + height > 1.0:
        raise ConfigError(f"{location} выходит за границы экрана")
    return x, y, width, height


def validate_user_config(config: dict[str, Any]) -> None:
    """Проверяет разрешённые пользователю параметры внешнего вида."""
    interface = require_mapping(config, "interface", "user_config")
    colors = require_mapping(interface, "colors", "user_config.interface")
    for color_name in ("background", "panel", "button", "button_active", "text", "status"):
        require_color(colors, color_name, "user_config.interface.colors")

    font = require_mapping(interface, "font", "user_config.interface")
    require_string(font, "family", "user_config.interface.font")
    for size_name in ("title_size", "subtitle_size", "button_size", "status_size"):
        require_integer(font, size_name, "user_config.interface.font", 8, 72)


def validate_admin_config(config: dict[str, Any]) -> None:
    """Проверяет параметры оболочки, профили мониторов и белый список кнопок."""
    shell = require_mapping(config, "shell", "admin_conf")
    require_string(shell, "title", "admin_conf.shell")
    require_string(shell, "subtitle", "admin_conf.shell")
    fullscreen = shell.get("fullscreen")
    if not isinstance(fullscreen, bool):
        raise ConfigError("admin_conf.shell.fullscreen должен быть true или false")
    require_string(shell, "initial_status", "admin_conf.shell")
    if require_string(shell, "title_weight", "admin_conf.shell") not in {"normal", "bold"}:
        raise ConfigError("admin_conf.shell.title_weight должен быть normal или bold")
    require_number(shell, "button_wrap_fraction", "admin_conf.shell", 0.3, 1.0)
    require_number(shell, "status_wrap_fraction", "admin_conf.shell", 0.3, 1.0)
    require_integer(shell, "application_poll_interval_ms", "admin_conf.shell", 100, 5000)
    log_path = Path(require_string(shell, "application_log_path", "admin_conf.shell"))
    if not log_path.is_absolute():
        raise ConfigError("admin_conf.shell.application_log_path должен быть абсолютным путём")

    text_positions = require_mapping(shell, "text_positions", "admin_conf.shell")
    for region_name in ("title", "subtitle", "status"):
        region = require_mapping(text_positions, region_name, "admin_conf.shell.text_positions")
        validate_position(region, f"admin_conf.shell.text_positions.{region_name}")

    display = require_mapping(config, "display", "admin_conf")
    active_profile = require_string(display, "active_profile", "admin_conf.display")
    profiles = require_mapping(display, "profiles", "admin_conf.display")
    if active_profile not in profiles:
        raise ConfigError(
            f"admin_conf.display.active_profile указывает на отсутствующий профиль: {active_profile}"
        )

    applications = config.get("applications")
    if not isinstance(applications, list) or not applications:
        raise ConfigError("admin_conf.applications должен быть непустым списком")

    seen_identifiers: set[str] = set()
    enabled_identifiers: set[str] = set()
    enabled_count = 0
    for position, application in enumerate(applications, start=1):
        location = f"admin_conf.applications[{position}]"
        if not isinstance(application, dict):
            raise ConfigError(f"{location} должен быть объектом")
        identifier = require_string(application, "id", location)
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,31}", identifier):
            raise ConfigError(f"{location}.id должен состоять из строчных латинских букв, цифр и _")
        if identifier in seen_identifiers:
            raise ConfigError(f"Повторяющийся идентификатор приложения: {identifier}")
        seen_identifiers.add(identifier)
        require_string(application, "label", location)
        require_string(application, "description", location)
        enabled = application.get("enabled")
        if not isinstance(enabled, bool):
            raise ConfigError(f"{location}.enabled должен быть true или false")
        enabled_count += int(enabled)
        if enabled:
            enabled_identifiers.add(identifier)

        button = require_mapping(application, "button", location)
        require_color(button, "background", f"{location}.button")
        require_color(button, "active_background", f"{location}.button")
        require_color(button, "foreground", f"{location}.button")
        require_string(button, "font_family", f"{location}.button")
        require_integer(button, "font_size", f"{location}.button", 8, 72)
        font_weight = require_string(button, "font_weight", f"{location}.button")
        if font_weight not in {"normal", "bold"}:
            raise ConfigError(f"{location}.button.font_weight должен быть normal или bold")
        if require_string(button, "relief", f"{location}.button") not in {
            "flat",
            "raised",
            "sunken",
            "ridge",
            "groove",
        }:
            raise ConfigError(f"{location}.button.relief содержит неизвестный стиль")

        launch = require_mapping(application, "launch", location)
        argv = launch.get("argv")
        if not isinstance(argv, list) or any(not isinstance(argument, str) for argument in argv):
            raise ConfigError(f"{location}.launch.argv должен быть списком строк")
        if any(not argument for argument in argv):
            raise ConfigError(f"{location}.launch.argv не должен содержать пустые строки")
        if argv and not Path(argv[0]).is_absolute():
            raise ConfigError(f"{location}.launch.argv[0] должен быть абсолютным путём")

    if not enabled_count:
        raise ConfigError("В admin_conf.applications должна быть включена хотя бы одна задача")

    for profile_id, profile in profiles.items():
        location = f"admin_conf.display.profiles.{profile_id}"
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,31}", profile_id):
            raise ConfigError(f"Некорректный идентификатор профиля монитора: {profile_id}")
        if not isinstance(profile, dict):
            raise ConfigError(f"{location} должен быть объектом")
        require_string(profile, "label", location)
        require_string(profile, "model", location)
        resolution = require_string(profile, "resolution", location)
        if not re.fullmatch(r"[1-9][0-9]{2,4}x[1-9][0-9]{2,4}", resolution):
            raise ConfigError(f"{location}.resolution должен иметь вид 1920x1080")
        orientation = require_string(profile, "orientation", location)
        if orientation not in {"landscape", "portrait"}:
            raise ConfigError(f"{location}.orientation должен быть landscape или portrait")
        require_number(profile, "ui_scale", location, 0.5, 2.0)

        positions = require_mapping(profile, "button_positions", location)
        if not enabled_identifiers.issubset(positions):
            missing_positions = sorted(enabled_identifiers - positions.keys())
            raise ConfigError(
                f"{location}.button_positions не содержит: {', '.join(missing_positions)}"
            )
        rectangles: list[tuple[str, float, float, float, float]] = []
        for identifier in enabled_identifiers:
            position_location = f"{location}.button_positions.{identifier}"
            position = require_mapping(positions, identifier, f"{location}.button_positions")
            rectangles.append((identifier, *validate_position(position, position_location)))

        for index, first in enumerate(rectangles):
            for second in rectangles[index + 1 :]:
                horizontal_overlap = first[1] < second[1] + second[3] and second[1] < first[1] + first[3]
                vertical_overlap = first[2] < second[2] + second[4] and second[2] < first[2] + first[4]
                if horizontal_overlap and vertical_overlap:
                    raise ConfigError(
                        f"Кнопки {first[0]} и {second[0]} перекрываются в профиле {profile_id}"
                    )


def load_configurations(user_path: Path, admin_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Загружает обе конфигурации и допускает запуск только после их проверки."""
    user_config = load_json_object(user_path)
    admin_config = load_json_object(admin_path)
    validate_user_config(user_config)
    validate_admin_config(admin_config)
    return user_config, admin_config
