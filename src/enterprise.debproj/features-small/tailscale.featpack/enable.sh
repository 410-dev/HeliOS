#!/bin/bash

# Get Ubuntu codename
. /etc/os-release
UBUNTU_CODENAME_LOWER=$(echo "$UBUNTU_CODENAME" | tr '[:upper:]' '[:lower:]')

# Install tailscale
set -e
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/"${UBUNTU_CODENAME_LOWER}".noarmor.gpg | sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/"${UBUNTU_CODENAME_LOWER}".tailscale-keyring.list | sudo tee /etc/apt/sources.list.d/tailscale.list
sudo apt update
sudo apt install tailscale -y
set +e

# Check if parameter contains --no-interaction
if [[ ! -z $(echo "$@" | grep \\--no-interaction) ]]; then
    echo "User selected not to use interactive token configuration."
    exit 0
fi


# Login
echo -n "Setup login? (y/n)"
read setup_login
if [[ "$setup_login" == "y" ]] || [[ "$setup_login" == "Y" ]]; then
    sudo tailscale login
fi
unset setup_login

# Enable system tray
echo -n "Enable system tray? (y/n)"
read enable_sys_tray
if [[ "$enable_sys_tray" == "y" ]] || [[ "$enable_sys_tray" == "Y" ]]; then
    sudo tailscale configure systray --enable-startup=systemd
fi
unset enable_sys_tray

# Use as TS operator
echo -n "Set current user ($(whoami)) as Tailscale operator? (y/n)"
read use_this_as_operator
if [[ "$use_this_as_operator" == "y" ]] || [[ "$use_this_as_operator" == "Y" ]]; then
    sudo tailscale set --operator="$(whoami)"
fi
unset use_this_as_operator

exit 0
