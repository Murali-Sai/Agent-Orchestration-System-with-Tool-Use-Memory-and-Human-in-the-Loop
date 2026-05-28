# Start the system without Docker (uses in-memory fallbacks for Redis/ChromaDB)
# Run from the project root

$env:PYTHONPATH = Get-Location

# Check for .env
if (-not (Test-Path ".env")) {
    Write-Host "ERROR: .env not found. Copy .env.example to .env and fill in ANTHROPIC_API_KEY." -ForegroundColor Red
    exit 1
}

# Load .env
Get-Content ".env" | ForEach-Object {
    if ($_ -match "^\s*([^#][^=]+)=(.*)$") {
        [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim())
    }
}

Write-Host "Starting FastAPI backend on http://localhost:8000 ..." -ForegroundColor Cyan
$api = Start-Process -NoNewWindow -FilePath "python" -ArgumentList "-m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload" -PassThru

Start-Sleep -Seconds 3

Write-Host "Starting Streamlit UI on http://localhost:8501 ..." -ForegroundColor Cyan
$ui = Start-Process -NoNewWindow -FilePath "python" -ArgumentList "-m streamlit run ui/app.py --server.port 8501" -PassThru

Write-Host ""
Write-Host "System running:" -ForegroundColor Green
Write-Host "  API:    http://localhost:8000" -ForegroundColor White
Write-Host "  UI:     http://localhost:8501" -ForegroundColor White
Write-Host "  Docs:   http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C to stop." -ForegroundColor Yellow

try {
    Wait-Process -Id $api.Id
} finally {
    Stop-Process -Id $api.Id -ErrorAction SilentlyContinue
    Stop-Process -Id $ui.Id -ErrorAction SilentlyContinue
}
