@echo off
echo ========================================
echo  IDP — Urban Infrastructure Prediction
echo  Starting Frontend (port 3000)
echo ========================================
cd /d "%~dp0frontend"
echo.
echo Frontend running at: http://localhost:3000/index.html
echo.
python -m http.server 3000
pause
