#!/bin/sh

find_python() {
	# If no suitable candidate is found in the first pass, we look for any
	# working interpreter in the second pass and let it display its own
	# error message about missing modules.
	for PYTHON_CMD in "$1" "pass"; do
		for PYTHON_EXEC in python3 python2 python; do
			if "$PYTHON_EXEC" -c "$PYTHON_CMD" >/dev/null 2>&1; then
				echo "$PYTHON_EXEC"
				return
			fi
		done
	done
}

PYTHON="$(find_python "import six; import pygame; import OpenGL")"
if [ ! "$PYTHON" ]; then
	echo "Error: Could not find any working Python interpreter." >&2
	exit 1
fi

cd "$(dirname "$0")/client"
exec "$PYTHON" client.py "$@"
