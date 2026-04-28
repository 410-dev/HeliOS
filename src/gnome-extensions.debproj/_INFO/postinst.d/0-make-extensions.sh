#!/bin/bash

# Gnome Clipboard History
set -e
echo "Building Gnome Clipboard History extension..."
cd /usr/share/gnome-shell/extensions/clipboard-history@alexsaveau.dev
make

echo "Building Blur My Shell extension..."
cd /usr/share/gnome-shell/extensions
unzip blur-my-shell@aunetx.shell-extension.zip -d blur-my-shell@aunetx
glib-schemas blur-my-shell@aunetx/schemas

set +e