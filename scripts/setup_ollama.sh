#!/bin/bash
# Pull recommended models for RTL Verify
set -euo pipefail

echo "=== RTL Verify: Ollama Model Setup ==="

# Check Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "ERROR: Ollama is not running. Start it with 'ollama serve'"
    exit 1
fi

# Pull recommended models
echo "Pulling qwen2.5-coder:7b (recommended for development)..."
ollama pull qwen2.5-coder:7b

echo ""
echo "=== Models Available ==="
curl -s http://localhost:11434/api/tags | python3 -m json.tool
