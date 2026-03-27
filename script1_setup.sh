#!/bin/bash
# Script 1: Install dependencies (run once to prepare the image)
set -e

pip install fastapi uvicorn httpx

echo "Setup complete. Image is ready to share."
