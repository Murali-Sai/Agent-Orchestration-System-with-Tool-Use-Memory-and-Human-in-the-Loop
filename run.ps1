# Run the full stack without Docker
Set-Location "D:\Multi-Agent Orchestration System"
$env:PYTHONPATH = "D:\Multi-Agent Orchestration System"

# Load .env
Get-Content ".env" | ForEach-Object {
    if ($_ -match "^\s*([^#=][^=]*)=(.+)$") {
        $k = $Matches[1].Trim(); $v = $Matches[2].Trim()
        [System.Environment]::SetEnvironmentVariable($k, $v, "Process")
        Set-Item "Env:\$k" $v
    }
}

Write-Host "Starting API on http://localhost:8000 ..." -ForegroundColor Cyan
$api = Start-Job -ScriptBlock {
    Set-Location "D:\Multi-Agent Orchestration System"
    $env:PYTHONPATH = "D:\Multi-Agent Orchestration System"
    Get-Content ".env" | ForEach-Object {
        if ($_ -match "^\s*([^#=][^=]*)=(.+)$") { Set-Item "Env:\$($Matches[1].Trim())" $Matches[2].Trim() }
    }
    python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
}

Start-Sleep -Seconds 5

Write-Host "Starting UI on http://localhost:8501 ..." -ForegroundColor Cyan
$ui = Start-Job -ScriptBlock {
    Set-Location "D:\Multi-Agent Orchestration System"
    $env:PYTHONPATH = "D:\Multi-Agent Orchestration System"
    Get-Content ".env" | ForEach-Object {
        if ($_ -match "^\s*([^#=][^=]*)=(.+)$") { Set-Item "Env:\$($Matches[1].Trim())" $Matches[2].Trim() }
    }
    python -m streamlit run ui/app.py --server.port 8501 --server.address 0.0.0.0
}

Write-Host ""
Write-Host "Both services running:" -ForegroundColor Green
Write-Host "  API : http://localhost:8000" -ForegroundColor White
Write-Host "  UI  : http://localhost:8501" -ForegroundColor White
Write-Host "  Docs: http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C to stop." -ForegroundColor Yellow

try { Wait-Job $api, $ui | Receive-Job -Wait } finally {
    Stop-Job $api, $ui -ErrorAction SilentlyContinue
    Remove-Job $api, $ui -ErrorAction SilentlyContinue
}
