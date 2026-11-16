@echo off
rem Lists every network address of this laptop, so you can pick the one the PHONE can reach.
rem Run it AFTER the USB tether / Wi-Fi are connected (the backend only prints its list at start-up).
echo.
echo Addresses of this laptop (use the one on the same network as the phone):
echo.
powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254*' } | ForEach-Object { '  ' + $_.InterfaceAlias.PadRight(14) + ' http://' + $_.IPAddress + ':8000' }"
echo.
echo USB tethering usually shows up as 'Ethernet 2' with an address like 192.168.42.x or 192.168.x.x.
echo The Radiomaster Wi-Fi address is NOT reachable from the phone - do not use it in the app.
echo.
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/api/health -TimeoutSec 3; 'Backend on this laptop: running' } catch { 'Backend on this laptop: NOT running - start tools\start_live.cmd' }"
