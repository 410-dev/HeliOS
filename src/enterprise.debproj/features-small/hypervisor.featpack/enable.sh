#!/bin/bash

set -e

apt install -y qemu-system-x86 libvirt-daemon-system libvirt-clients virtinst virt-manager bridge-utils
users=$(dsl System User List)
for user in $users; do
    usermod -aG libvirt "$user"
    usermod -aG kvm "$user"
done
systemctl enable --now libvirtd

# Copy current bundle patch/* to root
cp -r "$1/patch"/* /

set +e
