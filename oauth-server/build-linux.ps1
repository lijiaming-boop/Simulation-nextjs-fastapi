# Build OAuth Server for Linux
Write-Host "Building OAuth Server for Linux..." -ForegroundColor Green

$env:GOOS = "linux"
$env:GOARCH = "amd64"

Set-Location $PSScriptRoot
go build -o oauth-server cmd/main.go

if ($LASTEXITCODE -eq 0) {
    Write-Host "Build successful!" -ForegroundColor Green
    Write-Host "Output: oauth-server" -ForegroundColor Cyan
} else {
    Write-Host "Build failed!" -ForegroundColor Red
    exit 1
}

