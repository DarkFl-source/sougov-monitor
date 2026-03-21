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

if not exist "data\oportunidades.json" (
    echo.
    echo A base ainda nao existe. Execute primeiro a atualizacao.
    pause
    exit /b 1
)

echo ==========================================
echo Abrindo painel local
echo ==========================================
echo.
echo O Streamlit sera iniciado no navegador.
echo.

"%VENV_PYTHON%" -m streamlit run app.py
