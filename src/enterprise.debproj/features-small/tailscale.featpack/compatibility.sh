#!/bin/bash

# Check if curl exists
if [[ -z "$(which curl)" ]]; then
    echo "curl is required to install Tailscale."
    exit 1
fi

. /etc/os-release
UBUNTU_CODENAME_LOWER=$(echo "$UBUNTU_CODENAME" | tr '[:upper:]' '[:lower:]')
url="https://pkgs.tailscale.com/stable/ubuntu/${UBUNTU_CODENAME_LOWER}.tailscale-keyring.list"
if ! curl -fsSL --head "$url" | grep -q "200"; then
    echo "Error: Tailscale is not available for Ubuntu ${UBUNTU_CODENAME_LOWER}."
    exit 1
fi
