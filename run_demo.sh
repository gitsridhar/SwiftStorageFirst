#!/bin/bash
# Quick start script for Swift Server & Client demo

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║         OpenStack Swift Server & Client Demo                ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.7 or higher."
    exit 1
fi

echo "✓ Python 3 found: $(python3 --version)"
echo ""

# Check if dependencies are installed
echo "Checking dependencies..."
if ! python3 -c "import flask" 2>/dev/null; then
    echo "⚠️  Flask not found. Installing dependencies..."
    pip3 install -r requirements.txt
    echo ""
fi

echo "✓ Dependencies installed"
echo ""

# Start the server in background
echo "Starting Swift Server..."
python3 swift_server.py &
SERVER_PID=$!

# Wait for server to start
sleep 3

# Check if server is running
if ps -p $SERVER_PID > /dev/null; then
    echo "✓ Server started (PID: $SERVER_PID)"
    echo ""
    
    # Run the test suite
    echo "Running test suite..."
    echo ""
    python3 test_swift.py
    TEST_EXIT=$?
    
    echo ""
    echo "Stopping server..."
    kill $SERVER_PID
    
    if [ $TEST_EXIT -eq 0 ]; then
        echo "✓ Demo completed successfully!"
    else
        echo "❌ Demo encountered errors"
    fi
else
    echo "❌ Failed to start server"
    exit 1
fi

# Made with Bob
