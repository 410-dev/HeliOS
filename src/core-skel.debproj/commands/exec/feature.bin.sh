#!/bin/bash

# Wrapper script to call frameworkctl helios-features $@

if [ -z "$1" ]; then
	echo "Usage: $0 [enable|disable|list] [feature name]"
	exit 1
fi
frameworkctl helios-features "$@"