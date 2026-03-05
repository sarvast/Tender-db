@echo off
echo ==============================================
echo =   Starting GeM Tender Dashboard Locally    =
echo ==============================================
echo.

echo Activating virtual environment...
if exist "..\venv\Scripts\activate.bat" (
    call "..\venv\Scripts\activate.bat"
) else (
    echo [ERROR] Virtual environment not found at ..\venv
    pause
    exit /b
)

echo Starting FastAPI server on http://localhost:8080
echo.
echo Please leave this window open! Open your browser and go to:
echo http://localhost:8080
echo.

python -m uvicorn web_app:app --reload --host 127.0.0.1 --port 8080

pause
