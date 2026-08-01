#!/bin/bash
# Helper script to run commands in Windsurf integrated terminal
# Usage: .devin/terminal_helper.sh "command"

COMMAND="$1"
if [ -z "$COMMAND" ]; then
    echo "Usage: $0 \"command\""
    exit 1
fi

echo "Running in integrated terminal: $COMMAND"
eval "$COMMAND"
