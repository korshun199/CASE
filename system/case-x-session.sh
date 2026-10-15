#!/usr/bin/env bash
# Запускает пользовательскую оболочку CASE внутри уже поднятого X-сервера.

set -euo pipefail

# Постоянный путь к воспроизводимому проекту на Orange Pi.
PROJECT_ROOT="/home/work/CASE"
# Непривилегированная учётная запись пользователя терминала.
KIOSK_USER="case"

cd "$PROJECT_ROOT"
exec /usr/sbin/runuser -u "$KIOSK_USER" -- \
    /usr/bin/env HOME="/home/$KIOSK_USER" PATH="/usr/bin:/bin" \
    /usr/bin/python3 -m app.main
