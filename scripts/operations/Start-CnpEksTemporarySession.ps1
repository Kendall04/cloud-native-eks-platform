# Execute manually in Kendall's normal PowerShell terminal. No execution-policy change.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$taskPython = Get-Command python.exe -ErrorAction Stop
& $taskPython.Source -B (Join-Path $PSScriptRoot 'cnp_eks_temporary_session.py') start
if ($LASTEXITCODE -ne 0) { throw 'Temporary EKS session stopped; no credential details are emitted.' }
