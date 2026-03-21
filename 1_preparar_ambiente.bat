@echo off
setlocal
cd /d "%~dp0"

set "VENV_DIR=%~dp0.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "SYSTEM_PYTHON_CMD="
set "SYSTEM_PYTHON_ARGS="

call :resolve_python
if errorlevel 1 exit /b 1

echo ==========================================
echo Preparando ambiente local do projeto
echo ==========================================
echo.

if not exist "%VENV_PYTHON%" (
    echo Criando ambiente virtual em ".venv"...
    call "%SYSTEM_PYTHON_CMD%" %SYSTEM_PYTHON_ARGS% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo.
        echo Falha ao criar o ambiente virtual.
        pause
        exit /b 1
    )
)

echo Atualizando pip...
"%VENV_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 (
    echo.
    echo Falha ao atualizar o pip.
    pause
    exit /b 1
)

echo Instalando dependencias...
"%VENV_PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo Falha ao instalar as dependencias Python.
    pause
    exit /b 1
)

echo Instalando navegador do Playwright...
"%VENV_PYTHON%" -m playwright install chromium
if errorlevel 1 (
    echo.
    echo Falha ao instalar o navegador do Playwright.
    pause
    exit /b 1
)

echo.
echo Ambiente preparado com sucesso.
echo Python do projeto: "%VENV_PYTHON%"
pause
exit /b 0

:resolve_python
where py >nul 2>nul
if not errorlevel 1 (
    set "SYSTEM_PYTHON_CMD=py"
    set "SYSTEM_PYTHON_ARGS=-3"
    exit /b 0
)

where python >nul 2>nul
if not errorlevel 1 (
    set "SYSTEM_PYTHON_CMD=python"
    set "SYSTEM_PYTHON_ARGS="
    exit /b 0
)

echo Nenhum Python foi encontrado no PATH.
echo Instale o Python 3 e execute novamente este script.
pause
exit /b 1
