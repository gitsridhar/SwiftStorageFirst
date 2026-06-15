@echo off
REM Quick start script for Swift Server & Client demo (Windows)

echo ╔══════════════════════════════════════════════════════════════╗
echo ║         OpenStack Swift Server ^& Client Demo                ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed. Please install Python 3.7 or higher.
    exit /b 1
)

echo ✓ Python found
echo.

REM Check if dependencies are installed
echo Checking dependencies...
python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo ⚠️  Flask not found. Installing dependencies...
    pip install -r requirements.txt
    echo.
)

echo ✓ Dependencies installed
echo.

REM Start the server in background
echo Starting Swift Server...
start /B python swift_server.py

REM Wait for server to start
timeout /t 3 /nobreak >nul

echo ✓ Server started
echo.

REM Run the test suite
echo Running test suite...
echo.
python test_swift.py

echo.
echo Stopping server...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq swift_server.py*" >nul 2>&1

echo ✓ Demo completed!

@REM Made with Bob
