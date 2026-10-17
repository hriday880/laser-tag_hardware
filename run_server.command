#!/usr/bin/env bash
cd "$(dirname "$0")/server"
echo "Starting LaserTag Central Server..."
python3 server.py
