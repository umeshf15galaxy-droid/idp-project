@echo off
echo ========================================
echo  IDP — Urban Infrastructure Prediction
echo  Starting Backend (port 8000)
echo ========================================
cd /d "%~dp0backend"
echo.
echo Installing dependencies...
pip install -r requirements.txt
echo.
echo Starting FastAPI server...
echo API docs: http://localhost:8000/docs
echo.
uvicorn main:app --reload --host 0.0.0.0 --port 8000
pause
