# Kiosk launcher for the "ShopScheduleKiosk" scheduled task (see install.ps1).
# Waits for the local HTTP server to come up, then opens the browser in kiosk
# mode -- mirrors install-client.sh's retry-until-reachable loop, which is
# more robust than foreman-kiosk.service's flat 5-second sleep (that service
# gets away with a flat sleep because systemd's `After=foreman-server.service`
# ordering guarantees the server unit already started; a Task Scheduler
# AtLogOn trigger has no such ordering against the AtStartup server task, so
# a fixed delay isn't safe here -- retry until it actually answers instead).
param(
    [Parameter(Mandatory)][string]$BrowserPath,
    [string]$Url = 'http://localhost:8080/kiosk.html'
)

while ($true) {
    try {
        $null = Invoke-WebRequest -Uri 'http://localhost:8080/' -UseBasicParsing -TimeoutSec 3
        break
    } catch {
        Start-Sleep -Seconds 5
    }
}

& $BrowserPath --kiosk --noerrdialogs --disable-infobars --no-first-run `
    --disable-session-crashed-bubble --disable-restore-session-state $Url
