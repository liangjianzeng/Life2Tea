#!/bin/bash

# Start the OpenAI-compatible proxy service on port 3003
# This script runs on the remote server

cd /home/jianzengliang/MyWork/Life2Tea

# Activate virtual environment
source /home/jianzengliang/.local/venvs/proxy/bin/activate

# Start the proxy server
nohup /home/jianzengliang/.local/venvs/proxy/bin/python -m backend.app.routers.proxy_service --host 0.0.0.0 --port 3003 > /home/jianzengliang/MyWork/Life2Tea/log/proxy_service.log 2>&1 &

echo "Proxy service started on port 3003"
echo "Log file: /home/jianzengliang/MyWork/Life2Tea/log/proxy_service.log"

# Wait a moment for startup
sleep 2

# Check if running
if pgrep -f "proxy_service" > /dev/null; then
    echo "✓ Proxy service is running"
    curl -s http://localhost:3003/health | python3 -m json.tool
else
    echo "✗ Proxy service failed to start"
    cat /home/jianzengliang/MyWork/Life2Tea/log/proxy_service.log
fi
