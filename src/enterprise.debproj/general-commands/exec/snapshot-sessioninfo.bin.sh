#!/bin/bash

# Get the subvolume name (e.g., @snapshot-2025...)
CURRENT_SUBVOL=$(findmnt / -n -o SOURCE | sed 's/.*\[\/\(.*\)\]/\1/')

# 1. Check for Sandbox (OverlayFS)
if findmnt / | grep -q "overlay"; then
    echo "sandbox:$CURRENT_SUBVOL"
    exit 0
fi

# 2. Check for Snapshot (Read-Write)
# If the subvolume is NOT "@", we are in a snapshot
if [[ "$CURRENT_SUBVOL" != "@" ]]; then
    echo "rwsnapshot:$CURRENT_SUBVOL"
    exit 0
fi

# 3. Otherwise, we are on the main system
echo "main:@"
exit 0
