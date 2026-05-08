#!/bin/bash

# Gnome Clipboard History
set -e
echo "Building Gnome Clipboard History extension..."
cd /usr/share/gnome-shell/extensions/clipboard-history@alexsaveau.dev
make

echo "Building Blur My Shell extension..."
cd /usr/share/gnome-shell/extensions
unzip -o blur-my-shell@aunetx.shell-extension.zip -d blur-my-shell@aunetx
glib-compile-schemas blur-my-shell@aunetx/schemas

echo "Building Multi Monitor Bar extension..."
cd /usr/share/gnome-shell/extensions
unzip -o multi-monitors-bar@frederykabryan.zip -d multi-monitors-bar@frederykabryan
glib-compile-schemas multi-monitors-bar@frederykabryan/schemas

set +e