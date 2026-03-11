@echo off
REM Inicia Brave en segundo plano (headless). Para Zonaprop sin captcha suele ir mejor start_browser_for_scraper_visible.bat (ventana visible).
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
echo Brave en segundo plano (puerto 9222). Cierra Brave antes si esta abierto.
start "" "%BRAVE%" --headless=new --remote-debugging-port=9222 --user-data-dir="%USERDATA%" --profile-directory=Default --no-first-run --disable-background-networking --disable-default-apps --disable-sync --metrics-recording-only --no-default-browser-check
echo Listo. Deja esta ventana abierta o minimizada; el scraper se conectara al tocar Scrapear en la app.
pause
