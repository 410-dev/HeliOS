#!/bin/bash

# Wrapper script to call {{frameworks}}/<framework>.framework/controller
if [ -z "$1" ]; then
	echo "Usage: $0 <framework> [args...]"
	exit 1
fi
EXECUTABLE="{{frameworks}}/$1.framework/controller"
if [ ! -f "$EXECUTABLE" ]; then
	if [ ! -d "{{frameworks}}/$1.framework" ]; then
		echo "Error: Framework '$1' not found."
	else
		echo "Error: Framework '$1' is not a configurable framework."
	fi
	exit 1
fi
"$EXECUTABLE" "${@:2}"
