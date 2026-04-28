#!/usr/bin/env bash

set -euo pipefail

ask_reboot_gui() {
    zenity --question \
        --title="Restart Required" \
        --text="$1" \
        --ok-label="Reboot Now" \
        --cancel-label="Later"
}

ask_reboot_cli() {
    while true; do
        read -r -p "$1 [y/N]: " answer

        case "${answer:-N}" in
            y|Y|yes|YES|Yes)
                return 0
                ;;
            n|N|no|NO|No|"")
                return 1
                ;;
            *)
                echo "Please enter y or n."
                ;;
        esac
    done
}

reboot_system() {
    echo "Restarting..."

    if command -v systemctl >/dev/null 2>&1; then
        systemctl reboot
    else
        reboot
    fi
}

has_gui_session() {
    [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]
}

# Set message
if [[ -z "$1" ]]; then
	MESSAGE="A system restart is required to apply changes. Do you want to reboot now?"
else
	MESSAGE="$1"
fi

if has_gui_session && command -v zenity >/dev/null 2>&1; then
    if ask_reboot_gui "$MESSAGE"; then
        reboot_system
    else
        echo "Abort."
    fi
else
    if ask_reboot_cli "$MESSAGE"; then
        reboot_system
    else
        echo "Abort."
    fi
fi