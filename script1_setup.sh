#!/bin/bash
# Script 1: Clone repo and install dependencies (run once to prepare the image)
set -e

git clone git@github.com:Sodiride123/AI_quizforge.git /workspace/AI_quizforge
pip install fastapi uvicorn httpx

echo "Setup complete. Image is ready to share."
