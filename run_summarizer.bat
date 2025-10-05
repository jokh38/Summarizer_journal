@echo off
REM Journal Paper Summarizer - Windows Execution Script
REM This script runs the paper summarizer with proper environment setup

setlocal

REM Change to script directory
cd /d "%~dp0"

REM Activate virtual environment if it exists
if exist "venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call .venv\Scripts\activate.bat
) else (
    echo Warning: No virtual environment found. Using system Python.
)

REM Load environment variables from .env if it exists
if exist ".env" (
    echo Loading environment variables from .env...
    for /f "tokens=*" %%a in ('type .env ^| findstr /v "^#"') do set %%a
)

REM Create necessary directories
if not exist "logs" mkdir logs
if not exist "output" mkdir output
if not exist "data" mkdir data

REM Run the main script
echo Starting paper summarizer...
python main.py %*

REM Check exit code
if %ERRORLEVEL% EQU 0 (
    echo Paper summarizer completed successfully.
) else (
    echo Paper summarizer failed with exit code: %ERRORLEVEL% 1>&2
)

endlocal
exit /b %ERRORLEVEL%
