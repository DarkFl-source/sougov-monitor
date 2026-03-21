@echo off
setlocal
cd /d "%~dp0"

set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV_PYTHON%" (
    echo.
    echo O ambiente virtual ainda nao foi preparado.
    echo Execute primeiro "1_preparar_ambiente.bat".
    pause
    exit /b 1
)

echo ==========================================
echo Atualizando base de oportunidades SOUGOV
echo ==========================================
echo.

"%VENV_PYTHON%" scraper.py --headless
if errorlevel 1 (
    echo.
    echo Falha ao atualizar a base.
    pause
    exit /b 1
)

echo.
echo Base atualizada com sucesso.
pause
