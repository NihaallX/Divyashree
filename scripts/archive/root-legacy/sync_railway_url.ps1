# Auto-Update Railway with Cloudflare Tunnel URL
# Monitors Cloudflare tunnel and automatically updates Railway env var

Write-Host "Cloudflare -> Railway Auto-Sync Starting..." -ForegroundColor Cyan

# Check if Railway CLI is installed
if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] Railway CLI not found. Installing..." -ForegroundColor Yellow
    npm install -g @railway/cli
}

# Railway project/service IDs (get these from Railway dashboard URL)
# Example: https://railway.app/project/{PROJECT_ID}/service/{SERVICE_ID}
$RAILWAY_PROJECT_ID = $env:RAILWAY_PROJECT_ID
$RAILWAY_SERVICE_ID = $env:RAILWAY_SERVICE_ID

if (-not $RAILWAY_PROJECT_ID -or -not $RAILWAY_SERVICE_ID) {
    Write-Host "[INFO] Set Railway IDs in environment (optional):" -ForegroundColor Yellow
    Write-Host '   $env:RAILWAY_PROJECT_ID = "your-project-id"' -ForegroundColor White
    Write-Host '   $env:RAILWAY_SERVICE_ID = "your-service-id"' -ForegroundColor White
    Write-Host "`n   Or run: railway login" -ForegroundColor Cyan
}

$lastUrl = ""
$checkInterval = 30  # seconds

Write-Host "[OK] Starting monitor (checking every ${checkInterval}s)..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop`n" -ForegroundColor Gray

while ($true) {
    try {
        # Get Cloudflare URL from Docker logs
        $logs = docker logs relayx-cloudflare-tunnel 2>&1 | Select-String "https://.*\.trycloudflare\.com"
        
        if ($logs) {
            $currentUrl = ($logs | Select-Object -First 1).Line -replace '.*?(https://[^\s]+\.trycloudflare\.com).*', '$1'
            
            if ($currentUrl -ne $lastUrl -and $currentUrl -match "https://") {
                Write-Host "`n[CHANGE] URL Changed!" -ForegroundColor Yellow
                Write-Host "   Old: $lastUrl" -ForegroundColor Gray
                Write-Host "   New: $currentUrl" -ForegroundColor Green
                
                # Update Railway environment variable
                Write-Host "`n[UPDATE] Updating Railway..." -ForegroundColor Cyan
                
                $updateCommand = "railway variables --set VOICE_GATEWAY_URL=$currentUrl"
                
                if ($RAILWAY_SERVICE_ID) {
                    $updateCommand += " --service $RAILWAY_SERVICE_ID"
                }
                
                Invoke-Expression $updateCommand
                
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "[OK] Railway updated successfully!" -ForegroundColor Green
                    Write-Host "[WAIT] Railway is redeploying..." -ForegroundColor Yellow
                    $lastUrl = $currentUrl
                } else {
                    Write-Host "[ERROR] Failed to update Railway" -ForegroundColor Red
                }
            } else {
                $timestamp = Get-Date -Format "HH:mm:ss"
                Write-Host "[$timestamp] URL unchanged: $currentUrl" -ForegroundColor DarkGray
            }
        } else {
            Write-Host "[WARN] No Cloudflare URL found. Is tunnel running?" -ForegroundColor Yellow
        }
        
    } catch {
        Write-Host "[ERROR] $_" -ForegroundColor Red
    }
    
    Start-Sleep -Seconds $checkInterval
}
