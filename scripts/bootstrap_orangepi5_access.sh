#!/usr/bin/env bash

# Первичная настройка доступа к Orange Pi 5 по образцу CASE.
# Скрипт не копирует частные ключи и не изменяет VIDEOSCAN.

set -Eeuo pipefail

PI_HOST="${1:-192.168.20.120}"
PI_BOOTSTRAP_USER="orangepi"
KEY_BUNDLE="$(mktemp)"

cleanup() {
    rm -f -- "$KEY_BUNDLE"
}
trap cleanup EXIT

die() {
    echo "[ERROR] $*" >&2
    exit 1
}

mapfile -t PUBLIC_KEYS < <(find /home/oleg/.ssh -maxdepth 1 -type f -name '*.pub' -print | sort)
[[ "${#PUBLIC_KEYS[@]}" -gt 0 ]] || die "Не найдены публичные SSH-ключи в /home/oleg/.ssh"
cat "${PUBLIC_KEYS[@]}" > "$KEY_BUNDLE"

echo "[INFO] Настройка ${PI_HOST}. Частные ключи не передаются."
echo "[INFO] Сначала будет запрошен sudo-пароль пользователя ${PI_BOOTSTRAP_USER}."

# Проверяем sudo отдельным интерактивным сеансом, не смешивая пароль с stdin скрипта.
ssh -tt "$PI_BOOTSTRAP_USER@$PI_HOST" 'sudo -v'

ssh -tt "$PI_BOOTSTRAP_USER@$PI_HOST" 'sudo -n bash -s' <<'REMOTE_SCRIPT'
set -Eeuo pipefail

backup_dir="/root/case-access-backup-$(date +%Y%m%d-%H%M%S)"
install -d -m 700 "$backup_dir"
cp -a /etc/passwd /etc/group /etc/sudoers "$backup_dir/"
if [[ -f /etc/ssh/sshd_config ]]; then
    cp -a /etc/ssh/sshd_config "$backup_dir/"
fi

if ! id -u oleg >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash oleg
fi
usermod --append --groups sudo oleg
for group_name in dialout video input plugdev docker; do
    if getent group "$group_name" >/dev/null 2>&1; then
        usermod --append --groups "$group_name" oleg
    fi
done

install -d -m 700 -o oleg -g oleg /home/oleg/.ssh
chown -R oleg:oleg /home/oleg/.ssh
chmod 700 /home/oleg/.ssh
echo "[OK] Пользователь oleg создан/проверен и добавлен в sudo."
echo "[INFO] Резервная копия: $backup_dir"
REMOTE_SCRIPT

echo "[INFO] Теперь задай пароль пользователя oleg. Он не записывается в проект."
ssh -tt "$PI_BOOTSTRAP_USER@$PI_HOST" 'sudo -n passwd oleg'

echo "[INFO] Установка публичных ключей в /home/oleg/.ssh/authorized_keys"
ssh-copy-id -i "$KEY_BUNDLE" "oleg@$PI_HOST"

echo "[INFO] Проверка ключевого входа"
ssh -o BatchMode=yes -o ConnectTimeout=8 "oleg@$PI_HOST" \
    'id; groups; sudo -n -l 2>&1 || true'
echo "[OK] Базовая настройка доступа завершена."
