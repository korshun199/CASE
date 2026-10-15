#!/usr/bin/env bash
# Настраивает и проверяет киоск-службу CASE на Orange Pi.

set -euo pipefail

# Воспроизводимое расположение проекта на Orange Pi.
PROJECT_ROOT="/home/work/CASE"
# Системный каталог для root-части запуска киоска.
SYSTEM_LAUNCHER="/usr/local/lib/case/case-x-session"
# Имя управляемой systemd-службы.
SERVICE_NAME="case-kiosk.service"
# Отдельная непривилегированная учётная запись пользователя терминала.
KIOSK_USER="case"
# Файл полного журнала административного сценария.
LOG_FILE="$PROJECT_ROOT/answere.txt"

exec > >(tee "$LOG_FILE") 2>&1

print_usage() {
    # Печатает поддерживаемые административные действия.
    echo "Использование: bash run {configure-kiosk|status}"
}

backup_current_state() {
    # Сохраняет учётные и служебные файлы до изменения киоск-конфигурации.
    local timestamp
    local backup_dir
    timestamp="$(date +%Y%m%d-%H%M%S)"
    backup_dir="/root/case-kiosk-backup-$timestamp"

    sudo install -d -m 0700 "$backup_dir"
    for source_path in /etc/passwd /etc/group /etc/shadow /etc/gshadow \
        "/etc/systemd/system/$SERVICE_NAME" "$SYSTEM_LAUNCHER"; do
        if sudo test -e "$source_path"; then
            sudo cp -a "$source_path" "$backup_dir/"
        fi
    done
    echo "[INFO] Резервная копия: $backup_dir"
}

configure_kiosk() {
    # Создаёт отдельного пользователя, службу Xorg и безопасные права CASE.
    echo "=== CASE: настройка киоск-сессии ==="
    echo "Время: $(date --iso-8601=seconds)"
    echo "Цель: $SERVICE_NAME на tty1, оболочка от пользователя $KIOSK_USER"

    if ! sudo -v; then
        echo "[ERROR] Не удалось подтвердить права sudo."
        return 1
    fi

    backup_current_state

    if ! id "$KIOSK_USER" >/dev/null 2>&1; then
        sudo useradd --create-home --user-group --shell /usr/sbin/nologin "$KIOSK_USER"
        echo "[INFO] Создан непривилегированный пользователь $KIOSK_USER"
    else
        echo "[INFO] Пользователь $KIOSK_USER уже существует"
    fi
    sudo usermod --lock "$KIOSK_USER"

    sudo install -d -o root -g root -m 0755 /usr/local/lib/case
    sudo install -o root -g root -m 0755 \
        "$PROJECT_ROOT/system/case-x-session.sh" "$SYSTEM_LAUNCHER"
    sudo install -o root -g root -m 0644 \
        "$PROJECT_ROOT/system/case-kiosk.service" "/etc/systemd/system/$SERVICE_NAME"

    sudo chown -R root:root "$PROJECT_ROOT/app"
    sudo find "$PROJECT_ROOT/app" -type d -exec chmod 0755 {} +
    sudo find "$PROJECT_ROOT/app" -type f -exec chmod 0644 {} +
    sudo chown root:root "$PROJECT_ROOT/config/admin_conf.json"
    sudo chmod 0644 "$PROJECT_ROOT/config/admin_conf.json"
    sudo chown "$KIOSK_USER:$KIOSK_USER" "$PROJECT_ROOT/config/user_config.json"
    sudo chmod 0640 "$PROJECT_ROOT/config/user_config.json"

    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME"
    sudo systemctl restart "$SERVICE_NAME"
    sleep 4

    if ! sudo systemctl is-active --quiet "$SERVICE_NAME"; then
        echo "[ERROR] Киоск-служба не запустилась. Последние строки журнала:"
        sudo journalctl -u "$SERVICE_NAME" --no-pager -n 80
        return 1
    fi

    echo "[OK] Киоск-служба активна."
    sudo systemctl --no-pager --full status "$SERVICE_NAME" -n 20
}

show_status() {
    # Показывает актуальное состояние службы без изменения системы.
    sudo systemctl --no-pager --full status "$SERVICE_NAME" -n 40
}

case "${1:-}" in
    configure-kiosk)
        configure_kiosk
        ;;
    status)
        show_status
        ;;
    *)
        print_usage
        exit 2
        ;;
esac
