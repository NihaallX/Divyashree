# Start RelayX with Auto-Updating Cloudflare Tunnel
Write-Host "Starting RelayX with Auto-Updating Cloudflare Tunnel..." -ForegroundColor Cyan

# Start Docker containers
Write-Host "`n[1/3] Starting Docker services..." -ForegroundColor Yellow
docker-compose up -d

# Wait for services to be ready
Write-Host "`n[2/3] Waiting for services to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# Start Cloudflare URL auto-update monitor in background
Write-Host "`n[3/3] Starting Cloudflare URL auto-update monitor..." -ForegroundColor Yellow
$monitorJob = Start-Job -ScriptBlock {
    Set-Location $using:PSScriptRoot
    python voice_gateway/cloudflare_monitor.py
}

Write-Host "`n✅ RelayX Started!" -ForegroundColor Green
Write-Host "   - Backend: http://localhost:8000" -ForegroundColor White
Write-Host "   - Voice Gateway: http://localhost:8001" -ForegroundColor White
Write-Host "   - Cloudflare URL: Auto-updating" -ForegroundColor Green
Write-Host "`nCloudflare URL monitor is running in background (Job ID: $($monitorJob.Id))" -ForegroundColor Cyan
Write-Host "`nTo view monitor logs:" -ForegroundColor Yellow
Write-Host "   Receive-Job -Id $($monitorJob.Id) -Keep" -ForegroundColor White
Write-Host "`nTo stop all services:" -ForegroundColor Yellow
Write-Host "   docker-compose down" -ForegroundColor White
Write-Host "   Stop-Job -Id $($monitorJob.Id); Remove-Job -Id $($monitorJob.Id)" -ForegroundColor White
Write-Host "`nPress Ctrl+C to stop monitoring the logs...`n" -ForegroundColor Gray

# Monitor logs in foreground
try {
    while ($true) {
        $jobOutput = Receive-Job -Id $monitorJob.Id
        if ($jobOutput) {
            Write-Host $jobOutput
        }
        Start-Sleep -Seconds 2
        
        # Check if job is still running
        $jobState = (Get-Job -Id $monitorJob.Id).State
        if ($jobState -ne "Running") {
            Write-Host "`n⚠️ Monitor stopped. State: $jobState" -ForegroundColor Yellow
            break
        }
    }
} catch {
    Write-Host "`n👋 Stopping monitor..." -ForegroundColor Cyan
    Stop-Job -Id $monitorJob.Id
    Remove-Job -Id $monitorJob.Id
}
