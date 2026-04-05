param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$BaselineRef = "HEAD",
  [string]$BranchPrefix = "rh",
  [string[]]$Lanes = @("research", "build", "verify")
)

$ErrorActionPreference = "Stop"

function Resolve-SafePath {
  param(
    [Parameter(Mandatory = $true)][string]$Base,
    [Parameter(Mandatory = $true)][string]$Child
  )

  $resolved = [System.IO.Path]::GetFullPath((Join-Path $Base $Child))
  $rootResolved = [System.IO.Path]::GetFullPath($Base)
  if (-not $resolved.StartsWith($rootResolved, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to use path outside root: $resolved"
  }
  return $resolved
}

Set-Location $Root

git rev-parse --verify $BaselineRef | Out-Null

foreach ($lane in $Lanes) {
  $worktreeName = "$($lane)-rumbling-hedge"
  $worktreePath = Resolve-SafePath -Base (Split-Path $Root -Parent) -Child $worktreeName
  $branchName = "${BranchPrefix}/${lane}"

  if (Test-Path $worktreePath) {
    Write-Host "Skipping ${lane}: path already exists at $worktreePath"
    continue
  }

  git worktree add -b $branchName $worktreePath $BaselineRef
  Write-Host "Created $lane worktree at $worktreePath on branch $branchName"
}
