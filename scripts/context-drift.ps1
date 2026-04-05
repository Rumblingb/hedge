param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"
Set-Location $Root

Write-Host "== Context Drift Check =="

Write-Host "`nActive branch and status:"
git status --short --branch

Write-Host "`nWatch list:"
@(
  "docs/CONTEXT_DRIFT_CHECKLIST.md"
  "docs/CTO_OPERATING_MODEL.md"
  "docs/FOUNDER_INPUTS.md"
  "docs/RISK_GUARDRAILS.md"
  "docs/RESEARCH_MEMO_2026.md"
  "docs/AGENTIC_STACK_2026.md"
  "README.md"
) | ForEach-Object {
  if (Test-Path $_) {
    Write-Host " - $_"
  }
}

Write-Host "`nUse this sequence:"
Write-Host "  1. Read the context drift checklist"
Write-Host "  2. Review any repo or thesis changes"
Write-Host "  3. Run npm run verify"
Write-Host "  4. Freeze promotion if drift is detected"
