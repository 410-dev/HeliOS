#!/bin/bash

# Copy /etc/sket/Templates to ~/Template if it doesn't exist
if [ ! -d "$HOME/Templates" ]; then
	cp -r /etc/skel/Templates "$HOME/Templates"
fi
