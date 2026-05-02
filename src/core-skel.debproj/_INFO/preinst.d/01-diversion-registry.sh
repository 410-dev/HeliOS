#!/bin/bash

# Perform dpkg divert for existing logo file at

function divert() {
    local PATH_TO_DIVERT="$1"
    echo "Diverting $PATH_TO_DIVERT"
    dpkg-divert --package="$DPKG_MAINTSCRIPT_PACKAGE" --add --rename --divert "$PATH_TO_DIVERT".diverted "$PATH_TO_DIVERT"
}

#divert "/usr/share/icons/hicolor/scalable/places/distributor-logo.svg"
#divert "/usr/share/icons/Yaru/scalable/places/start-here-symbolic.svg"
#divert "/etc/os-release"
#divert "/usr/share/plymouth/ubuntu-logo.png"
#divert "/usr/share/pixmaps/ubuntu-logo-text.png"
#divert "/usr/share/pixmaps/ubuntu-logo-text-dark.png"

unset -f divert
