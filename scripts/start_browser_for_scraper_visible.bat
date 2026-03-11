@echo off
REM Brave VISIBLE (sin headless) para el scraper en Docker. Recomendado para Zonaprop sin captcha.
REM Se abre una ventana que podes minimizar; el scraper se conecta por puerto 9222.
REM Cierra Brave antes de ejecutar este .bat.

set "BRAVE="
if exist "C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe" set "BRAVE=C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
if exist "C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe" set "BRAVE=C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe"
if "%BRAVE%"=="" (
    echo No se encontro Brave. Instalalo o edita este .bat con la ruta correcta.
    pause
    exit /b 1
)

set "USERDATA=%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data"
echo Iniciando Brave visible (puerto 9222). Minimizalo; no lo cierres mientras scrapeas.
start "" "%BRAVE%" --remote-debugging-port=9222 --user-data-dir="%USERDATA%" --profile-directory=Default --no-first-run --no-default-browser-check
echo Listo. El scraper se conectara al tocar Scrapear en la app.
pause
