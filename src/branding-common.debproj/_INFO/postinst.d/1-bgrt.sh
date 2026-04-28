#!/bin/bash
echo "Enabling BGRT..."
set -e
sudo update-alternatives --install /usr/share/plymouth/themes/default.plymouth default.plymouth /usr/share/plymouth/themes/helios/helios.plymouth 100
sudo update-alternatives --set default.plymouth /usr/share/plymouth/themes/helios/helios.plymouth
sudo update-initramfs -u
set +e
echo "BGRT enabled."