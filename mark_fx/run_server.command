#!/usr/bin/env bash
# ================================================================
#          LASER TAG CENTRAL REFEREE SERVER LAUNCHER
# ================================================================

# Navigate to server directory
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -d "$DIR/server" ]; then
    cd "$DIR/server"
elif [ -d "$DIR/../server" ]; then
    cd "$DIR/../server"
fi

clear
echo "=================================================="
echo "       🚀 STARTING LASER TAG MATCH SERVER        "
echo "=================================================="
echo "Directory: $(pwd)"
echo "Port:      5050"
echo "Dashboard: http://localhost:5050"
echo "=================================================="
echo ""
echo "Opening dashboard in your web browser..."

# Open web dashboard in default browser (Safari/Chrome)
(sleep 1.5 && open "http://localhost:5050") &

# Start the Python Referee Server
python3 server.py
