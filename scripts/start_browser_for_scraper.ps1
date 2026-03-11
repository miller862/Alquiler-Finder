# Inicia Brave en segundo plano (headless) con remote debugging para que el scraper
# en Docker use tu perfil y Zonaprop no pida captcha.
# Ejecutá esto en PowerShell y dejalo corriendo mientras usás la app.
# Luego en docker-compose.yml descomentá: SCRAPER_BROWSER_URL: host.docker.internal:9222

$bravePaths = @(
    "C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe"
)
$brave = $bravePaths | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $brave) {
    Write-Error "No se encontró Brave. Instalalo o ajustá la ruta en este script."
    exit 1
}

$userData = "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\User Data"
Write-Host "Iniciando Brave en segundo plano (puerto 9222). Cerrá Brave antes de ejecutar este script."
& $brave --headless=new --remote-debugging-port=9222 --user-data-dir=$userData --profile-directory=Default --no-first-run --disable-background-networking --disable-default-apps --disable-sync --metrics-recording-only --no-default-browser-check
Write-Host "Brave terminado."
