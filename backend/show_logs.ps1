param(
    [int]$Tail = 80,
    [switch]$Follow
)

$ErrorActionPreference = 'Stop'
$LogRoot = $PSScriptRoot
$Logs = Get-ChildItem -LiteralPath $LogRoot -Filter '*.log' -File |
    Sort-Object LastWriteTime -Descending

if (-not $Logs) {
    Write-Host "No .log files found in $LogRoot"
    exit 0
}

Write-Host "Available logs:"
$Logs | ForEach-Object {
    Write-Host ("- {0} ({1})" -f $_.Name, $_.LastWriteTime)
}

Write-Host ""
Write-Host ("Showing last {0} lines from {1}" -f $Tail, $Logs[0].Name)

if ($Follow) {
    Get-Content -LiteralPath $Logs[0].FullName -Tail $Tail -Wait
} else {
    Get-Content -LiteralPath $Logs[0].FullName -Tail $Tail
}
