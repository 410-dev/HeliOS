#!/bin/bash

if [[ "$1" == "gui" ]]; then
    sudo systemctl set-default graphical.target
    sudo systemctl start gdm
    sudo chvt 0
elif [[ "$1" == "cli" ]]; then
    sudo chvt 4
    sudo systemctl set-default multi-user.target
    sudo systemctl isolate multi-user.target
    sleep 5
    sudo systemctl stop gdm
else
    echo "Usage: interface.sh [gui|cli]"
    echo "  gui - Switch to graphical user interface"
    echo "  cli - Switch to command line interface"
    exit 1
fi

