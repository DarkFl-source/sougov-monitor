@echo off
setlocal
cd /d "%~dp0"

set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"
set "CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe"
set "CHROME_PROFILE_DIR=D:\Temp\chrome-sougov"
set "SOUGOV_URL=https://sougov.sigepe.gov.br/sougov/"

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
echo 3 - Abrir Chrome manual para login no SOUGOV
echo 4 - Conectar ao Chrome manual ja autenticado
echo 5 - Abrir relatorio local
echo 6 - Atualizar base e abrir relatorio
echo 7 - Fazer commit e push
echo 8 - Sair
echo.
set /p opcao=Escolha uma opcao: 

if "%opcao%"=="1" goto scrape
if "%opcao%"=="2" goto scrape_login
if "%opcao%"=="3" goto open_manual_chrome
if "%opcao%"=="4" goto scrape_attach
if "%opcao%"=="5" goto relatorio
if "%opcao%"=="6" goto tudo
if "%opcao%"=="7" goto git_publish
if "%opcao%"=="8" goto fim

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

:open_manual_chrome
cls
echo ==========================================
echo Abrindo Chrome manual para login
echo ==========================================
echo.
if not exist "%CHROME_PATH%" (
    echo Chrome nao foi encontrado em:
    echo %CHROME_PATH%
    echo.
    echo Ajuste o caminho no arquivo 2_executar_solucao.bat.
    pause
    goto menu
)
if not exist "%CHROME_PROFILE_DIR%" (
    mkdir "%CHROME_PROFILE_DIR%" >nul 2>nul
)
start "" "%CHROME_PATH%" --remote-debugging-port=9222 --user-data-dir="%CHROME_PROFILE_DIR%" "%SOUGOV_URL%"
echo Chrome aberto.
echo.
echo 1. Faca o login no SOUGOV nessa janela.
echo 2. Depois volte aqui e escolha a opcao 4 para anexar o scraping.
echo.
pause
goto menu

:scrape_attach
call :run_scraper --attach-cdp http://127.0.0.1:9222 --headless
goto menu

:relatorio
call :run_report
goto menu

:tudo
call :run_scraper --headless
if errorlevel 1 goto menu
call :run_report
goto menu

:git_publish
cls
echo ==========================================
echo Fazendo commit e push
echo ==========================================
echo.
git status --short
echo.
set /p commit_msg=Mensagem do commit (Enter para usar padrao): 
if "%commit_msg%"=="" set "commit_msg=Update SOUGOV app and dataset"

git add -A
if errorlevel 1 (
    echo.
    echo Falha ao preparar os arquivos para commit.
    pause
    goto menu
)

git diff --cached --quiet
if not errorlevel 1 (
    echo Nenhuma alteracao nova para commit.
    echo Tentando apenas sincronizar com o remoto...
    git push
    if errorlevel 1 (
        echo.
        echo Falha no push.
        pause
        goto menu
    )
    echo.
    echo Push concluido com sucesso.
    pause
    goto menu
)

git commit -m "%commit_msg%"
if errorlevel 1 (
    echo.
    echo Falha ao criar o commit.
    pause
    goto menu
)

git push
if errorlevel 1 (
    echo.
    echo O commit foi criado, mas o push falhou.
    pause
    goto menu
)

echo.
echo Commit e push concluidos com sucesso.
pause
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
