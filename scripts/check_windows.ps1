$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root
$env:PYTHONPATH = Join-Path $root "src"

Write-Host "API PureCheck Windows check"
Write-Host "Root: $root"
Write-Host ""

Write-Host "Python version:"
python --version

Write-Host ""
Write-Host "CLI version:"
python -m api_purecheck --version

Write-Host ""
Write-Host "Dry run:"
python -m api_purecheck check --config examples/config.example.json --dry-run

Write-Host ""
Write-Host "Profiles:"
python -m api_purecheck profiles

Write-Host ""
Write-Host "Tests:"
python -W error -m unittest discover -s tests

Write-Host ""
Write-Host "Checking generated artifacts..."
$pycache = Get-ChildItem -Recurse -Force -Directory -Filter __pycache__ -ErrorAction SilentlyContinue
if ($pycache) {
  Write-Host "Warning: __pycache__ directories exist after tests. They are ignored by git."
}

Write-Host ""
Write-Host "Check completed."
