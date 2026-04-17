#!/bin/bash

# Uninstall tailscale
set -e
sudo apt remove --purge tailscale -y
sudo rm -f /etc/apt/sources.list.d/tailscale.list
sudo rm -f /usr/share/keyrings/tailscale-archive-keyring.gpg
sudo apt update
set +e
