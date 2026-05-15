#!/bin/bash

# Unpack {{install}}/node-x64.tar.gz to {{install}}/node
arch=$(uname -m)
if [[ "$arch" == "x86_64" ]]; then
    echo "Detected architecture: x86_64"
    POSTFIX="x64"
elif [[ "$arch" == "aarch64" ]]; then
    echo "Detected architecture: aarch64"
    POSTFIX="arm64"
else
    echo "Unsupported architecture: $arch"
    exit 1
fi
echo "Unpacking node-$POSTFIX.tar.gz..."
mkdir -p {{install}}/node
tar -xzf {{install}}/node-$POSTFIX.tar.gz -C {{install}}/node --strip-components=1
echo "Unpacked node-$POSTFIX.tar.gz."
