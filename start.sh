#!/bin/bash
cd "$(dirname "$0")"

LOG_FILE="logs/acim.log"

echo "Starting ACIM Daily Minute... (logging to $LOG_FILE)"
echo "Schedule: daily at 2:00 AM Central"
echo "Press Ctrl+C to stop"
echo ""

python3 main.py "$@"
