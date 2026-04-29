#!/bin/bash

# Wrapper script to call {{frameworks}}/<framework>.framework/<framework>.apprunx
if [ -z "$1" ]; then
	echo "Usage: $0 <framework> [args...]"
	exit 1
fi
EXECUTABLE="{{frameworks}}/$1.framework/$1.apprunx"
if [ ! -f "$EXECUTABLE" ]; then
	if [ ! -d "{{frameworks}}/$1.framework" ]; then
		echo "Error: Framework '$1' not found."
	else
		echo "Error: Framework '$1' is not a runnable framework."
	fi
	exit 1
fi
apprun3 "$EXECUTABLE" "${@:2}"
