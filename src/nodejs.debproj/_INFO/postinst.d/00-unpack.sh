#!/bin/bash

# Unpack {{install}}/node-x64.tar.gz to {{install}}/node
arch=$(uname -m)
if [[ "$arch" == "x86_64" ]]; then
    echo "Detected architecture: x86_64"
    SUFFIX="x64"
elif [[ "$arch" == "aarch64" ]]; then
    echo "Detected architecture: aarch64"
    SUFFIX="arm64"
else
    echo "Unsupported architecture: $arch"
    exit 1
fi
echo "Unpacking node-$SUFFIX.tar.xz..."
mkdir -p "{{install}}/26.1.0"
tar -xJf "{{install}}/node-$SUFFIX.tar.xz" -C "{{install}}/26.1.0" --strip-components=1
ln -sf "{{install}}/26.1.0" "{{install}}/latest"
echo "Unpacked node-$SUFFIX.tar.xz."
