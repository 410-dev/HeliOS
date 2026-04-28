#!/bin/bash

# For each in  ~/.config/os.helios.postlogonconfig/enable-gnome-extensions/*, enable the extension with gnome-extensions enable <extension-name>

if [[ -d ~/.config/os.helios.postlogonconfig/enable-gnome-extensions/ ]]; then
	for extension in ~/.config/os.helios.postlogonconfig/enable-gnome-extensions/*; do
		if [[ -f "$extension" ]]; then
			extension_name=$(basename "$extension")
			echo "Enabling GNOME extension: $extension_name"
			gnome-extensions enable "$extension_name"
		fi
	done
else
	echo "No extensions to enable. Directory ~/.config/os.helios.postlogonconfig/enable-gnome-extensions/ does not exist."
fi
