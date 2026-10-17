"""Экран лаконичного состояния оборудования и служб CASE."""

from __future__ import annotations

import glob
import platform
import shutil
import socket
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any

from app.configuration import ConfigError, load_configurations


# Корень проекта и стандартные конфигурационные файлы оболочки.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
USER_CONFIG_PATH = PROJECT_ROOT / "config" / "user_config.json"
ADMIN_CONFIG_PATH = PROJECT_ROOT / "config" / "admin_conf.json"


def read_text(path: str, fallback: str = "нет данных") -> str:
    """Безопасно читает небольшой системный файл без выхода за пределы интерфейса."""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip("\x00\n ") or fallback
    except OSError:
        return fallback


def format_bytes(value: int) -> str:
    """Переводит байты в компактное значение для карточки состояния."""
    units = ("Б", "КиБ", "МиБ", "ГиБ", "ТиБ")
    number = float(value)
    for unit in units:
        if number < 1024 or unit == units[-1]:
            return f"{number:.1f} {unit}"
        number /= 1024
    return "нет данных"


def read_memory(path: str) -> tuple[str, str, float]:
    """Возвращает занятость оперативной памяти и процент использования."""
    values: dict[str, int] = {}
    try:
        for line in Path(path).read_text(encoding="ascii").splitlines():
            name, separator, raw_value = line.partition(":")
            if separator and raw_value.strip().endswith("kB"):
                values[name] = int(raw_value.strip()[:-2]) * 1024
    except (OSError, ValueError):
        return "нет данных", "warning", 0.0
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", 0)
    if not total:
        return "нет данных", "warning", 0.0
    used = total - available
    percent = used * 100 / total
    return f"{format_bytes(used)} / {format_bytes(total)} ({percent:.0f}%)", "ok" if percent < 85 else "warning", percent / 100


def read_temperature(path_pattern: str) -> tuple[str, str, float]:
    """Читает максимальную температуру доступных thermal-зон."""
    temperatures: list[float] = []
    for path in glob.glob(path_pattern):
        try:
            temperatures.append(int(Path(path).read_text(encoding="ascii").strip()) / 1000)
        except (OSError, ValueError):
            continue
    if not temperatures:
        return "нет датчика", "warning", 0.0
    maximum = max(temperatures)
    state = "ok" if maximum < 70 else "warning" if maximum < 80 else "error"
    return f"{maximum:.1f} °C", state, min(maximum / 100, 1.0)


def read_uptime(path: str) -> str:
    """Форматирует время работы системы из procfs."""
    try:
        seconds = int(float(Path(path).read_text(encoding="ascii").split()[0]))
    except (OSError, IndexError, ValueError):
        return "нет данных"
    days, seconds = divmod(seconds, 86400)
    hours, minutes = divmod(seconds, 3600)
    minutes, _ = divmod(minutes, 60)
    if days:
        return f"{days} дн. {hours} ч."
    return f"{hours} ч. {minutes} мин."


def service_state(service_id: str) -> tuple[str, str]:
    """Проверяет только заранее разрешённую systemd-службу без shell-команд."""
    try:
        result = subprocess.run(
            ["/usr/bin/systemctl", "is-active", service_id],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "недоступна", "warning"
    state = result.stdout.strip() or "неактивна"
    return state, "ok" if state == "active" else "error" if state == "failed" else "warning"


def local_ipv4() -> str:
    """Определяет основной IPv4-адрес без отправки сетевого пакета."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return ""
    finally:
        probe.close()


def collect_status(admin_config: dict[str, Any], screen_size: str) -> list[tuple[str, str, str, float | None]]:
    """Собирает компактный список показателей для четырёх карточек экрана."""
    status_config = admin_config["system_status"]
    paths = status_config["paths"]
    model = read_text(paths["model"], platform.machine())
    memory, memory_state, memory_ratio = read_memory(paths["memory"])
    temperature, temperature_state, temperature_ratio = read_temperature(paths["thermal_glob"])
    disk = shutil.disk_usage("/")
    disk_percent = disk.used * 100 / disk.total
    host = socket.gethostname()
    address_text = local_ipv4() or "нет IPv4"
    cameras = glob.glob(paths["camera_glob"])
    usb_devices = [path for path in glob.glob(paths["usb_glob"]) if read_text(path, "")]
    profile = admin_config["display"]["profiles"][admin_config["display"]["active_profile"]]
    display_text = f"{screen_size} / профиль {profile['resolution']}"

    result: list[tuple[str, str, str, float | None]] = [
        ("Плата", model, "ok", None),
        ("Система", f"{platform.release()} • {read_uptime(paths['uptime'])}", "ok", None),
        ("Температура", temperature, temperature_state, temperature_ratio),
        ("Память", memory, memory_state, memory_ratio),
        ("Диск", f"{format_bytes(disk.used)} / {format_bytes(disk.total)} ({disk_percent:.0f}%)", "ok" if disk_percent < 85 else "warning", disk_percent / 100),
        ("Сеть", f"{host} • {address_text}", "ok" if address_text != "нет IPv4" else "warning", None),
        ("Экран", display_text, "ok", None),
        ("Камеры", f"{len(cameras)} устройств", "ok" if cameras else "warning", None),
        ("USB", f"{len(usb_devices)} устройств", "ok" if usb_devices else "warning", None),
    ]
    for service in status_config["services"]:
        state, state_color = service_state(service["id"])
        result.append((service["label"], state, state_color, 1.0 if state == "active" else 0.0))
    return result


class SystemStatusApp(tk.Tk):
    """Показывает состояние прибора и возвращает пользователя в главное меню."""

    def __init__(self, user_config: dict[str, Any], admin_config: dict[str, Any]) -> None:
        """Создаёт полноэкранный экран статуса с кнопкой возврата."""
        super().__init__()
        self.user_config = user_config
        self.admin_config = admin_config
        self.status_config = admin_config["system_status"]
        self.colors = user_config["interface"]["colors"]
        self.font = user_config["interface"]["font"]
        self.configure(background=self.colors["background"], cursor="left_ptr")
        self.attributes("-fullscreen", True)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.title(self.status_config["title"])
        self.content = tk.Frame(self, background=self.colors["background"])
        self.content.pack(expand=True, fill="both", padx=54, pady=34)
        self.build_static_layout()
        self.refresh()

    def build_static_layout(self) -> None:
        """Создаёт заголовок, сетку карточек и нижнюю кнопку управления."""
        tk.Label(
            self.content,
            text=self.status_config["title"],
            font=(self.font["family"], self.font["title_size"], "bold"),
            foreground=self.colors["text"],
            background=self.colors["background"],
        ).pack(pady=(0, 2))
        tk.Label(
            self.content,
            text=self.status_config["subtitle"],
            font=(self.font["family"], self.font["subtitle_size"]),
            foreground=self.colors["status"],
            background=self.colors["background"],
        ).pack(pady=(0, 18))
        self.cards = tk.Frame(self.content, background=self.colors["background"])
        self.cards.pack(expand=True, fill="both")
        for column in range(2):
            self.cards.columnconfigure(column, weight=1)
        for row in range(7):
            self.cards.rowconfigure(row, weight=1)
        self.card_labels: list[tuple[tk.Label, tk.Label, tk.Label, tk.Canvas]] = []
        for index in range(14):
            card = tk.Frame(self.cards, background=self.status_config["colors"]["card"], padx=20, pady=11)
            card.grid(row=index // 2, column=index % 2, sticky="nsew", padx=8, pady=7)
            indicator = tk.Label(card, text="●", font=(self.font["family"], 22), background=card["background"])
            indicator.pack(side="left", padx=(0, 12))
            text_frame = tk.Frame(card, background=card["background"])
            text_frame.pack(side="left", fill="both", expand=True)
            label = tk.Label(text_frame, anchor="w", font=(self.font["family"], 13, "bold"), background=card["background"])
            label.pack(fill="x")
            value = tk.Label(text_frame, anchor="w", justify="left", wraplength=620, font=(self.font["family"], 14), background=card["background"])
            value.pack(fill="both", expand=True)
            progress = tk.Canvas(text_frame, height=8, highlightthickness=0, background=card["background"])
            progress.pack(fill="x", pady=(8, 0))
            self.card_labels.append((indicator, label, value, progress))
        ttk.Button(self.content, text="Главное меню", command=self.close).pack(pady=(18, 0), ipadx=24, ipady=8)

    def refresh(self) -> None:
        """Обновляет показания и планирует следующее обновление."""
        screen_size = f"{self.winfo_screenwidth()}×{self.winfo_screenheight()}"
        statuses = collect_status(self.admin_config, screen_size)
        status_colors = self.status_config["colors"]
        for index, (label, value, state, ratio) in enumerate(statuses[: len(self.card_labels)]):
            indicator, label_widget, value_widget, progress = self.card_labels[index]
            indicator.configure(foreground=status_colors.get(state, status_colors["muted"]))
            label_widget.configure(text=label, foreground=self.colors["text"])
            value_widget.configure(text=value, foreground=self.colors["status"])
            progress.delete("all")
            if ratio is not None:
                progress.update_idletasks()
                width = max(progress.winfo_width(), 1)
                progress.create_rectangle(0, 0, width, 8, fill=status_colors["bar_background"], outline="")
                progress.create_rectangle(0, 0, width * max(0.0, min(ratio, 1.0)), 8, fill=status_colors.get(state, status_colors["muted"]), outline="")
        for index in range(len(statuses), len(self.card_labels)):
            indicator, label_widget, value_widget, progress = self.card_labels[index]
            indicator.configure(foreground=status_colors["muted"])
            label_widget.configure(text="", foreground=self.colors["text"])
            value_widget.configure(text="", foreground=self.colors["status"])
            progress.delete("all")
        self.after(self.status_config["refresh_interval_ms"], self.refresh)

    def close(self) -> None:
        """Закрывает экран статуса с возвратом в главное меню CASE."""
        self.destroy()


def main() -> int:
    """Загружает конфигурацию и показывает экран состояния."""
    try:
        user_config, admin_config = load_configurations(USER_CONFIG_PATH, ADMIN_CONFIG_PATH)
    except ConfigError as error:
        print(f"[ERROR] Конфигурация экрана состояния: {error}")
        return 2
    app = SystemStatusApp(user_config, admin_config)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
