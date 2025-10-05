#!/usr/bin/env bash
# Journal Paper Summarizer - Execution Script
# This script runs the paper summarizer with proper environment setup

set -euo pipefail

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Activate virtual environment if it exists
if [ -d "venv/bin" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
elif [ -d ".venv/bin" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
else
    echo "Warning: No virtual environment found. Using system Python."
fi

# Load environment variables if .env exists
if [ -f ".env" ]; then
    echo "Loading environment variables from .env..."
    export $(grep -v '^#' .env | xargs)
fi

# Create necessary directories
mkdir -p logs output data

# Run the main script
echo "Starting paper summarizer..."
python3 main.py "$@"

# Capture exit code
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "Paper summarizer completed successfully."
else
    echo "Paper summarizer failed with exit code: $EXIT_CODE" >&2
fi

exit $EXIT_CODE
