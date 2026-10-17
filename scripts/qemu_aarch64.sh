#!/usr/bin/env bash

# Безопасный запуск ARM64-образа в QEMU для проверки Linux-части.
# Источник открывается в режиме snapshot и не должен быть /dev/*.

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_IMAGE="/home/oleg/Downloads/Orangepi5_1.2.4_debian_bookworm_server_linux6.1.99.img"
DEFAULT_ARCHIVE="/home/oleg/Downloads/Orangepi5_1.2.4_debian_bookworm_server_linux6.1.99.7z"
FIRMWARE="/usr/share/qemu-efi-aarch64/QEMU_EFI.fd"
TEMP_DIR=''

error() {
    echo "[ERROR] $*" >&2
    exit 1
}

info() {
    echo "[INFO] $*"
}

cleanup_temp() {
    if [[ -n "${TEMP_DIR:-}" && -d "$TEMP_DIR" ]]; then
        rm -rf -- "$TEMP_DIR"
    fi
}

check_tools() {
    command -v qemu-system-aarch64 >/dev/null 2>&1 || error "Не найден qemu-system-aarch64."
    [[ -f "$FIRMWARE" ]] || error "Не найден ARM64 UEFI: $FIRMWARE"
    info "QEMU: $(qemu-system-aarch64 --version | head -n 1)"
    info "UEFI: $FIRMWARE"
    info "Архитектура хоста: $(uname -m)"
}

check_image() {
    local image="$1"
    [[ -f "$image" ]] || error "IMG-файл не найден: $image"
    [[ "$image" != /dev/* ]] || error "Запуск с блочного устройства запрещён: $image"
    [[ "$(stat -c '%s' "$image")" -gt 0 ]] || error "IMG-файл пустой: $image"
    info "Образ: $image ($(stat -c '%s' "$image") байт)"
}

run_image() {
    local image="${1:-$DEFAULT_IMAGE}"
    check_tools
    check_image "$image"
    info "Запуск в QEMU snapshot: исходный IMG не изменяется."
    info "Для выхода из QEMU: Ctrl+A, затем X."
    qemu-system-aarch64 \
        -machine virt \
        -cpu cortex-a72 \
        -m 2048 \
        -smp 4 \
        -bios "$FIRMWARE" \
        -drive "file=$image,format=raw,if=virtio,snapshot=on" \
        -nographic
}

run_archive() {
    local archive="${1:-$DEFAULT_ARCHIVE}"
    local image_count image
    command -v 7z >/dev/null 2>&1 || error "Не найден 7z."
    [[ -f "$archive" ]] || error "Архив не найден: $archive"
    info "Проверка архива: $archive"
    7z t "$archive" >/dev/null || error "Архив повреждён или не читается."
    TEMP_DIR="$(mktemp -d /home/oleg/Downloads/qemu-orangepi5.XXXXXX)"
    trap cleanup_temp EXIT
    info "Извлечение IMG во временный каталог: $TEMP_DIR"
    7z x -y "$archive" "-o$TEMP_DIR" >/dev/null || error "Не удалось извлечь архив."
    image_count="$(find "$TEMP_DIR" -type f -iname '*.img' | wc -l)"
    [[ "$image_count" == '1' ]] || error "Ожидался один IMG-файл, найдено: $image_count"
    image="$(find "$TEMP_DIR" -type f -iname '*.img' -print -quit)"
    run_image "$image"
}

MODE="${1:-check}"
case "$MODE" in
    check)
        check_tools
        ;;
    boot)
        run_image "${2:-$DEFAULT_IMAGE}"
        ;;
    boot-archive)
        run_archive "${2:-$DEFAULT_ARCHIVE}"
        ;;
    *)
        echo "Использование: $0 check|boot [путь-к-img]|boot-archive [путь-к-7z]" >&2
        exit 2
        ;;
esac
