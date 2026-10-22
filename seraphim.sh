#!/bin/sh
# Run without installing: ./seraphim.sh synth examples/sentence1.sera -o out.wav
# Uses the project venv (with spaCy for `translate`) when it exists.
here="$(dirname "$(readlink -f "$0")")"
py=python3
[ -x "$here/.venv/bin/python" ] && py="$here/.venv/bin/python"
PYTHONPATH="$here${PYTHONPATH:+:$PYTHONPATH}" exec "$py" -m seraphim "$@"
