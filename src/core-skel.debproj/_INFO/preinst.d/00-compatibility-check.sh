#!/bin/bash

function keyread() {
    local file="$1"
    if [[ -f "/tmp/$file" ]]; then
        cat "/tmp/$file" | tr -d ' \t\n\r'
    else
        echo "0"
    fi
}

# Bypass keys:
#  All keys live in /tmp/
#  - BypassBTRFSCheck         : If content is "1", bypass btrfs filesystem check
#  - BypassBootPartitionCheck : If content is "1", bypass /boot separate partition check
#  - BypassHostOSCheck        : If content is "1", bypass host OS version check

# Check if current system is installed in btrfs filesystem
# If not, it is incompatible
if [ "$(keyread BypassBTRFSCheck)" != "1" ]; then
    if [ "$(findmnt -n -o FSTYPE /)" != "btrfs" ]; then
        echo "Error: The root filesystem is not BTRFS. This system is incompatible."
        exit 1
    fi
fi

# Check if /boot is not mounted as separate partition
# If so, then it is incompatible (Meaning: /boot MUST be a separate partition)
if [ "$(keyread BypassBootPartitionCheck)" != "1" ]; then
    if ! mountpoint -q /boot; then
        echo "Error: /boot is not mounted as a separate partition. This system is incompatible."
        exit 1
    fi
fi


# Host requirement: Ubuntu 26.04 LTS ONLY
# User may bypass version checking by creating a file at BypassHostOSCheck with content "1"
if [ "$(keyread BypassHostOSCheck)" != "1" ]; then
    if [ ! -f /etc/os-release ] || [ -z "$(grep "26.04" /etc/os-release)" ]; then
        echo "This package is intended for Ubuntu 26.04 LTS only. Aborting installation." >&2
        exit 1
    fi
fi

echo "System compatibility check passed."

