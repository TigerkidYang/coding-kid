param(
    [string]$JobName = "coding-kid-luna-max-full",
    [int]$Concurrency = 1
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path "$PSScriptRoot/../..").Path
$Harbor = Join-Path $PSScriptRoot ".venv312/Scripts/harbor.exe"
$Wheel = Get-ChildItem "$PSScriptRoot/dist/coding_kid-*.whl" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

foreach ($name in @("CODING_KID_BENCH_API_KEY", "CODING_KID_BENCH_BASE_URL")) {
    if (-not (Test-Path "Env:$name")) {
        throw "$name is required"
    }
}
if (-not (Test-Path -LiteralPath $Harbor -PathType Leaf)) {
    throw "Harbor environment is missing: $Harbor"
}
if (-not $Wheel) {
    throw "Build the Coding Kid wheel before starting the benchmark"
}

$taskRoot = "$PSScriptRoot/task-inspection/full/terminal-bench-2-1"
$missing = @(
    Get-ChildItem -LiteralPath $taskRoot -Directory |
        ForEach-Object {
            $taskFile = Join-Path $_.FullName "task.toml"
            $line = Get-Content -LiteralPath $taskFile |
                Where-Object { $_ -match '^docker_image\s*=\s*"(.+)"' } |
                Select-Object -First 1
            if ($line -match '^docker_image\s*=\s*"(.+)"') {
                docker image inspect $Matches[1] *> $null
                if ($LASTEXITCODE -ne 0) { $Matches[1] }
            }
        }
)
if ($missing.Count -gt 0) {
    throw "Refusing automatic pulls; $($missing.Count) task images are missing"
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = $PSScriptRoot
$env:CODING_KID_BENCH_WHEEL = $Wheel.FullName
$env:PIP_INDEX_URL = "https://mirrors.aliyun.com/pypi/simple/"

$jobPath = Join-Path $PSScriptRoot "jobs/$JobName"
if (Test-Path (Join-Path $jobPath "config.json")) {
    & $Harbor job resume --job-path $jobPath
} else {
    & $Harbor run `
        --dataset terminal-bench/terminal-bench-2-1 `
        --agent-import-path coding_kid_harbor:CodingKidAgent `
        --model gpt-5.6-luna `
        --n-attempts 5 `
        --n-concurrent $Concurrency `
        --no-force-build `
        --yes `
        --jobs-dir "$PSScriptRoot/jobs" `
        --job-name $JobName
}

if ($LASTEXITCODE -ne 0) {
    throw "Harbor exited with code $LASTEXITCODE"
}
