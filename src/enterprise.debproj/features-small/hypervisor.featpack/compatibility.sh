#!/bin/bash

# Check if virtualization is available
result="$(lscpu | grep Virtualization)"
if [[ -z "$result" ]]; then
    echo "Virtualization not supported on this system."
    exit 1
fi
echo "Virtualization supported: $result"
exit 0