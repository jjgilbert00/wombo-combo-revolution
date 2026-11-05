# Runs Wombo Combo's static checks and unit tests on a pull request's code (or any git ref), in a
# throwaway copy: the checkout and its branches aren't touched. Uses this checkout's .venv. Never runs
# the UI checks (they open the app's window).
#
#   powershell -ExecutionPolicy Bypass -File test-pr.ps1 35                        a PR's latest code
#   powershell -ExecutionPolicy Bypass -File test-pr.ps1 35 test_key_inputs.py     one test file
#   powershell -ExecutionPolicy Bypass -File test-pr.ps1 35 -Keep                  keep the copy, to add a test
#   powershell -ExecutionPolicy Bypass -File test-pr.ps1 C:\...\wombo-review-ab12 test_x.py   rerun in it
param(
    [Parameter(Mandatory = $true, Position = 0)][string]$Target,
    [Parameter(Position = 1)][string]$Pattern,
    [switch]$Keep
)
$ErrorActionPreference = 'Stop'
# The main checkout (also from a worktree), where .venv lives.
$common = git -C $PSScriptRoot rev-parse --path-format=absolute --git-common-dir
$repo = Split-Path -Parent $common
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { Write-Error "No .venv in $repo (see docs/BUILDING.md)"; exit 2 }

if (Test-Path $Target -PathType Container) {
    $work = $Target
} else {
    if ($Target -match '^\d+$') {
        git -C $repo fetch -q origin "pull/$Target/head"
        $ref = git -C $repo rev-parse FETCH_HEAD
    } else {
        $ref = git -C $repo rev-parse $Target
    }
    $work = Join-Path ([IO.Path]::GetTempPath()) ('wombo-review-' + [guid]::NewGuid().ToString('N').Substring(0, 6))
    git -C $repo archive --format=zip -o "$work.zip" $ref
    Expand-Archive "$work.zip" $work
    Remove-Item "$work.zip"
    "Testing $($ref.Substring(0, 7))"
    if ($Keep) { "Kept the copy at $work. Run its tests again with: test-pr.ps1 $work [test file]. Delete it when done." }
}
Push-Location $work
try {
    if ($Pattern) { & $python -m unittest discover -s tests -t tests -p $Pattern }
    else { & $python tools\check_all.py --unit }
    $code = $LASTEXITCODE
} finally {
    Pop-Location
    if (-not $Keep -and $work -ne $Target) { Remove-Item -Recurse -Force $work }
}
exit $code
