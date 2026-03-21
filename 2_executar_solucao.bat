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

:menu
cls
echo ==========================================
echo Solucao SOUGOV
echo ==========================================
echo.
echo 1 - Iniciar novo scraping com sessao salva
echo 2 - Iniciar novo scraping com novo login manual
echo 3 - Abrir relatorio local
echo 4 - Atualizar base e abrir relatorio
echo 5 - Sair
echo.
set /p opcao=Escolha uma opcao: 

if "%opcao%"=="1" goto scrape
if "%opcao%"=="2" goto scrape_login
if "%opcao%"=="3" goto relatorio
if "%opcao%"=="4" goto tudo
if "%opcao%"=="5" goto fim

echo.
echo Opcao invalida.
pause
goto menu

:scrape
call :run_scraper --headless
goto menu

:scrape_login
call :run_scraper --refresh-login
goto menu

:relatorio
call :run_report
goto menu

:tudo
call :run_scraper --headless
if errorlevel 1 goto menu
call :run_report
goto menu

:run_scraper
cls
echo ==========================================
echo Executando scraping
echo ==========================================
echo.
"%VENV_PYTHON%" scraper.py %*
if errorlevel 1 (
    echo.
    echo O scraping terminou com erro.
    pause
    exit /b 1
)
echo.
echo Scraping finalizado com sucesso.
pause
exit /b 0

:run_report
if not exist "data\oportunidades.json" (
    echo.
    echo A base ainda nao existe. Rode o scraping primeiro.
    pause
    exit /b 1
)
cls
echo ==========================================
echo Abrindo relatorio local
echo ==========================================
echo.
echo O navegador deve abrir automaticamente com o Streamlit.
echo Para encerrar, feche esta janela ou use Ctrl+C.
echo.
"%VENV_PYTHON%" -m streamlit run app.py
exit /b %errorlevel%

:fim
exit /b 0
