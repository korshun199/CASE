"""Первый графический прототип терминальной оболочки CASE."""

from __future__ import annotations

import argparse
import stat
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import Any

from app.configuration import ConfigError, load_configurations


# Корень исходного проекта, вычисляемый относительно файла оболочки.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Стандартный путь к пользовательской конфигурации.
DEFAULT_USER_CONFIG = PROJECT_ROOT / "config" / "user_config.json"
# Стандартный путь к административной конфигурации.
DEFAULT_ADMIN_CONFIG = PROJECT_ROOT / "config" / "admin_conf.json"


class CaseShell(tk.Tk):
    """Отрисовывает pointer-first главное меню без доступа к системному рабочему столу."""

    def __init__(self, user_config: dict[str, Any], admin_config: dict[str, Any]) -> None:
        """Создаёт окно и применяет уже проверенные параметры интерфейса."""
        super().__init__()
        self.user_config = user_config
        self.admin_config = admin_config
        self.colors = user_config["interface"]["colors"]
        self.font_settings = user_config["interface"]["font"]
        self.shell_settings = admin_config["shell"]
        self.display_settings = admin_config["display"]
        self.display_profile = self.display_settings["profiles"][
            self.display_settings["active_profile"]
        ]
        self.active_process: subprocess.Popen[bytes] | None = None
        self.process_log = None
        self.status_value = tk.StringVar(value=self.shell_settings["initial_status"])

        self.title(self.shell_settings["title"])
        self.configure(background=self.colors["background"])
        self.geometry(self.display_profile["resolution"])
        self.attributes("-fullscreen", self.shell_settings["fullscreen"])
        self.tk.call(
            "tk",
            "scaling",
            float(self.tk.call("tk", "scaling")) * self.display_profile["ui_scale"],
        )
        self.protocol("WM_DELETE_WINDOW", self.show_close_blocked)
        actual_resolution = f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}"
        if actual_resolution != self.display_profile["resolution"]:
            self.status_value.set(
                f"Выбран профиль «{self.display_profile['label']}» "
                f"({self.display_profile['resolution']}), фактический режим дисплея "
                f"{actual_resolution}. Проверьте профиль монитора."
            )
        self.build_menu()

    def build_menu(self) -> None:
        """Размещает заголовок и кнопки по нормированным координатам профиля дисплея."""
        title_font = (
            self.font_settings["family"],
            self.font_settings["title_size"],
            self.shell_settings["title_weight"],
        )
        subtitle_font = (self.font_settings["family"], self.font_settings["subtitle_size"])
        status_font = (self.font_settings["family"], self.font_settings["status_size"])
        text_positions = self.shell_settings["text_positions"]

        tk.Label(
            self,
            text=self.shell_settings["title"],
            font=title_font,
            foreground=self.colors["text"],
            background=self.colors["background"],
        ).place(**{f"rel{key}": value for key, value in text_positions["title"].items()})
        tk.Label(
            self,
            text=self.shell_settings["subtitle"],
            font=subtitle_font,
            foreground=self.colors["text"],
            background=self.colors["background"],
        ).place(**{f"rel{key}": value for key, value in text_positions["subtitle"].items()})

        for application in self.admin_config["applications"]:
            if application["enabled"]:
                button_style = application["button"]
                button_position = self.display_profile["button_positions"][application["id"]]
                button = tk.Button(
                    self,
                    text=application["label"],
                    font=(
                        button_style["font_family"],
                        button_style["font_size"],
                        button_style["font_weight"],
                    ),
                    foreground=button_style["foreground"],
                    background=button_style["background"],
                    activebackground=button_style["active_background"],
                    activeforeground=button_style["foreground"],
                    relief=button_style["relief"],
                    command=lambda selected=application: self.select_application(selected),
                    wraplength=int(
                        self.winfo_screenwidth() * self.shell_settings["button_wrap_fraction"]
                    ),
                    justify="center",
                )
                button.place(**{f"rel{key}": value for key, value in button_position.items()})

        tk.Label(
            self,
            textvariable=self.status_value,
            font=status_font,
            foreground=self.colors["status"],
            background=self.colors["background"],
            wraplength=int(
                self.winfo_screenwidth() * self.shell_settings["status_wrap_fraction"]
            ),
            justify="center",
        ).place(**{f"rel{key}": value for key, value in text_positions["status"].items()})

    def select_application(self, application: dict[str, Any]) -> None:
        """Запускает настроенную команду напрямую и возвращает меню после её завершения."""
        argv = application["launch"]["argv"]
        if not argv:
            self.status_value.set(
                f"{application['label']}: приложение пока не подключено. "
                f"{application['description']}"
            )
            return

        try:
            self.validate_trusted_executable(Path(argv[0]))
            log_path = Path(self.shell_settings["application_log_path"])
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self.process_log = log_path.open("ab")
            self.active_process = subprocess.Popen(
                argv,
                cwd=PROJECT_ROOT,
                stdin=subprocess.DEVNULL,
                stdout=self.process_log,
                stderr=subprocess.STDOUT,
                shell=False,
                close_fds=True,
            )
        except (OSError, ValueError) as error:
            if self.process_log is not None:
                self.process_log.close()
                self.process_log = None
            self.status_value.set(f"Не удалось запустить «{application['label']}»: {error}")
            return

        self.status_value.set(f"Запущено: {application['label']}")
        self.withdraw()
        self.after(
            self.shell_settings["application_poll_interval_ms"], self.check_application_process
        )

    def validate_trusted_executable(self, executable_path: Path) -> None:
        """Разрешает только root-owned исполняемый файл в недоступных для записи каталогах."""
        resolved_path = executable_path.resolve(strict=True)
        executable_stat = resolved_path.stat()
        if not stat.S_ISREG(executable_stat.st_mode) or executable_stat.st_uid != 0:
            raise PermissionError("исполняемый файл должен быть обычным файлом владельца root")
        if not executable_stat.st_mode & 0o111 or executable_stat.st_mode & 0o022:
            raise PermissionError("исполняемый файл должен запускаться и не быть доступным для записи группе/всем")
        for parent_path in resolved_path.parents:
            parent_stat = parent_path.stat()
            if parent_stat.st_uid != 0 or parent_stat.st_mode & 0o022:
                raise PermissionError(
                    f"каталог {parent_path} должен принадлежать root и быть защищён от записи группой/всеми"
                )

    def check_application_process(self) -> None:
        """Ждёт завершения приложения и восстанавливает то же главное меню CASE."""
        if self.active_process is None:
            return
        return_code = self.active_process.poll()
        if return_code is None:
            self.after(
                self.shell_settings["application_poll_interval_ms"],
                self.check_application_process,
            )
            return

        if self.process_log is not None:
            self.process_log.close()
            self.process_log = None
        self.active_process = None
        self.deiconify()
        self.lift()
        self.focus_force()
        if return_code == 0:
            self.status_value.set("Программа завершена. Выберите следующую задачу.")
            return

        error_text = f"Программа завершилась с ошибкой (код {return_code}). Открыто главное меню CASE."
        self.status_value.set(error_text)
        messagebox.showerror("Ошибка приложения", error_text, parent=self)

    def show_close_blocked(self) -> None:
        """Не позволяет кнопке закрытия передать пользователя рабочему столу."""
        messagebox.showinfo(
            "CASE",
            "Пользовательская сессия работает через главное меню CASE.",
            parent=self,
        )


def parse_arguments() -> argparse.Namespace:
    """Разбирает пути конфигурации, сохраняя стандартный запуск из корня проекта."""
    parser = argparse.ArgumentParser(description="Первый графический прототип CASE")
    parser.add_argument("--user-config", type=Path, default=DEFAULT_USER_CONFIG)
    parser.add_argument("--admin-config", type=Path, default=DEFAULT_ADMIN_CONFIG)
    return parser.parse_args()


def main() -> int:
    """Загружает конфигурацию и запускает окно либо сообщает понятную ошибку."""
    arguments = parse_arguments()
    try:
        user_config, admin_config = load_configurations(
            arguments.user_config, arguments.admin_config
        )
    except ConfigError as error:
        print(f"[ERROR] Конфигурация CASE: {error}", file=sys.stderr)
        return 2

    try:
        shell = CaseShell(user_config, admin_config)
    except tk.TclError as error:
        print(f"[ERROR] Графическая сессия CASE недоступна: {error}", file=sys.stderr)
        return 3
    shell.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
