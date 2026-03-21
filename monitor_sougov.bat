@echo off
setlocal
cd /d "%~dp0"

:menu
cls
echo ==========================================
echo Monitor SOUGOV
echo ==========================================
echo.
echo 1 - Atualizar base (usa sessao salva)
echo 2 - Atualizar base com novo login manual
echo 3 - Abrir painel de relatorio
echo 4 - Atualizar base e abrir painel
echo 5 - Sair
echo.
set /p opcao=Escolha uma opcao: 

if "%opcao%"=="1" goto atualizar
if "%opcao%"=="2" goto atualizar_login
if "%opcao%"=="3" goto painel
if "%opcao%"=="4" goto atualizar_e_painel
if "%opcao%"=="5" goto fim

echo.
echo Opcao invalida.
pause
goto menu

:atualizar
call atualizar_base.bat
goto menu

:atualizar_login
call atualizar_base_com_login.bat
goto menu

:painel
call abrir_painel.bat
goto menu

:atualizar_e_painel
call atualizar_base.bat
if errorlevel 1 goto menu
call abrir_painel.bat
goto menu

:fim
exit /b 0
