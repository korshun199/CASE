"""Единая проверка структуры и конфигурации первого прототипа CASE."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Callable

from app.configuration import ConfigError, load_configurations, validate_admin_config


PROJECT_ROOT = Path(__file__).resolve().parent
USER_CONFIG_PATH = PROJECT_ROOT / "config" / "user_config.json"
ADMIN_CONFIG_PATH = PROJECT_ROOT / "config" / "admin_conf.json"
MENU_APPLICATION_PATH = PROJECT_ROOT / "app" / "main.py"


def check_required_paths() -> None:
    """Проверяет постоянные файлы, без которых прототип не запускается."""
    required_paths = (USER_CONFIG_PATH, ADMIN_CONFIG_PATH, MENU_APPLICATION_PATH)
    missing_paths = [str(path.relative_to(PROJECT_ROOT)) for path in required_paths if not path.is_file()]
    if missing_paths:
        raise RuntimeError("Не найдены обязательные файлы: " + ", ".join(missing_paths))


def check_configurations() -> None:
    """Проверяет обе конфигурации общей строгой схемой приложения."""
    load_configurations(USER_CONFIG_PATH, ADMIN_CONFIG_PATH)


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
        ("Отклонение недопустимого размера текста кнопки", check_invalid_admin_configuration_is_rejected),
        ("Отклонение небезопасного формата команды запуска", check_invalid_launch_command_is_rejected),
        ("Отклонение перекрывающихся кнопок", check_overlapping_buttons_are_rejected),
        ("Синтаксис главного меню", check_menu_module),
    )
    results = [run_check(name, check) for name, check in checks]
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
