$ErrorActionPreference = "Stop"

$pythonExec = ".\backend\venv\Scripts\python.exe"

Write-Host "Starting AI NVR Backend Services..."

# Array of services and ports
$services = @(
    @{ Name="auth_service"; Port=8001; Module="auth_service.main:app" },
    @{ Name="camera_service"; Port=8002; Module="camera_service.main:app" },
    @{ Name="stream_service"; Port=8003; Module="stream_service.main:app" },
    @{ Name="event_service"; Port=8004; Module="event_service.main:app" },
    @{ Name="telegram_service"; Port=8005; Module="telegram_service.main:app" },
    @{ Name="archive_service"; Port=8006; Module="archive_service.main:app" }
)

foreach ($svc in $services) {
    Write-Host "Starting $($svc.Name) on port $($svc.Port)..."
    # Start process in a new window to keep them running
    Start-Process -FilePath $pythonExec -ArgumentList "-m", "uvicorn", $svc.Module, "--host", "0.0.0.0", "--port", $svc.Port -WorkingDirectory ".\backend"
}

Write-Host "All backend services launched in separate windows."
