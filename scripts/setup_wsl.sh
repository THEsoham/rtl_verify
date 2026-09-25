#!/bin/bash
# Setup script for WSL2 verification environment
# Run: wsl bash scripts/setup_wsl.sh

set -euo pipefail

echo "=== RTL Verify: WSL2 Environment Setup ==="

# Update packages
sudo apt-get update

# Install Icarus Verilog
echo "Installing Icarus Verilog..."
sudo apt-get install -y iverilog
iverilog -V | head -1
echo "iverilog installed successfully"

# Install Verilator
echo "Installing Verilator..."
sudo apt-get install -y verilator
verilator --version
echo "verilator installed successfully"

# Install optional tools
echo "Installing optional tools..."
sudo apt-get install -y gtkwave  # Waveform viewer

echo ""
echo "=== Setup Complete ==="
echo "iverilog: $(which iverilog)"
echo "vvp: $(which vvp)"
echo "verilator: $(which verilator)"
