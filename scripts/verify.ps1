param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [switch]$IncludeResearch = $true
)

$ErrorActionPreference = "Stop"
Set-Location $Root

function Invoke-Step {
  param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$Command,
    [Parameter(Mandatory = $true)][string[]]$Arguments
  )

  Write-Host "`n==> $Name"
  & $Command @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "$Name failed with exit code $LASTEXITCODE"
  }
}

Invoke-Step -Name "typecheck" -Command "npm" -Arguments @("run", "typecheck")
Invoke-Step -Name "tests" -Command "npm" -Arguments @("test")

if ($IncludeResearch) {
  Invoke-Step -Name "research" -Command "npm" -Arguments @("run", "research")
}

Invoke-Step -Name "sim" -Command "npm" -Arguments @("run", "sim")
