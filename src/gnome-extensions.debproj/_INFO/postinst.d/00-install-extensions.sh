#!/bin/bash

set -e
#echo "Building Gnome Clipboard History extension..."
#cd /usr/share/gnome-shell/extensions/clipboard-history@alexsaveau.dev
#make

echo "Building Gnome Clipboard extension... (Credit: https://github.com/foss-desk/gnome-clipboard)"
cd /usr/share/gnome-shell/extensions
unzip -o gnome-clipboard-main.zip -d gnome-clipboard@foss-desk.d
mv gnome-clipboard@foss-desk.d/gnome-clipboard-main gnome-clipboard@foss-desk
rm -r gnome-clipboard@foss-desk.d
cd gnome-clipboard@foss-desk
export PATH="$PATH:/usr/lib/node/latest/bin/"
make install
make enable


echo "Building Blur My Shell extension... (Credit: https://github.com/aunetx/blur-my-shell)"
cd /usr/share/gnome-shell/extensions
unzip -o blur-my-shell@aunetx.shell-extension.zip -d blur-my-shell@aunetx
glib-compile-schemas blur-my-shell@aunetx/schemas

echo "Building Multi Monitor Bar extension... (Credit: https://github.com/FrederykAbryan/multi-monitors-bar_fapv2)"
cd /usr/share/gnome-shell/extensions
unzip -o multi-monitors-bar@frederykabryan.zip -d multi-monitors-bar@frederykabryan
glib-compile-schemas multi-monitors-bar@frederykabryan/schemas

echo "Building Pinned Apps in AppGrid... (Credit: https://github.com/brunos3d/pinned-apps-in-appgrid)"
cd /usr/share/gnome-shell/extensions/pinned-apps-in-appgrid
make

set +e