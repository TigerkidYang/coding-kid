param(
    [int]$AttemptsPerTask = 5,
    [int]$MaximumInfrastructureRetries = 3
)

$ErrorActionPreference = "Stop"
$Harbor = Join-Path $PSScriptRoot ".venv312/Scripts/harbor.exe"
$TaskRoot = Join-Path $PSScriptRoot "task-inspection/full/terminal-bench-2-1"
$JobsRoot = Join-Path $PSScriptRoot "jobs/resumable-full"
$Wheel = Get-ChildItem "$PSScriptRoot/dist/coding_kid-*.whl" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
$MirrorPrefixes = @(
    "dockerproxy.net",
    "docker.1ms.run",
    "docker.m.daocloud.io",
    "docker.xuanyuan.me",
    "docker.1panel.live"
)

foreach ($name in @("CODING_KID_BENCH_API_KEY", "CODING_KID_BENCH_BASE_URL")) {
    if (-not (Test-Path "Env:$name")) { throw "$name is required" }
}
if (-not (Test-Path -LiteralPath $Harbor -PathType Leaf)) {
    throw "Harbor environment is missing: $Harbor"
}
if (-not $Wheel) { throw "Build the Coding Kid wheel before starting the benchmark" }

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = $PSScriptRoot
$env:CODING_KID_BENCH_WHEEL = $Wheel.FullName
$env:PIP_INDEX_URL = "https://mirrors.aliyun.com/pypi/simple/"
New-Item -ItemType Directory -Force -Path $JobsRoot | Out-Null

function Get-TaskImage([string]$TaskPath) {
    $line = Get-Content -LiteralPath (Join-Path $TaskPath "task.toml") |
        Where-Object { $_ -match '^docker_image\s*=\s*"(.+)"' } |
        Select-Object -First 1
    if ($line -notmatch '^docker_image\s*=\s*"(.+)"') {
        throw "No docker_image in $TaskPath/task.toml"
    }
    return $Matches[1]
}

function Ensure-TaskImage([string]$Image) {
    docker image inspect $Image *> $null
    if ($LASTEXITCODE -eq 0) { return }
    foreach ($prefix in $MirrorPrefixes) {
        $candidate = "$prefix/$Image"
        Write-Host "Pulling $candidate"
        & docker pull $candidate
        if ($LASTEXITCODE -eq 0) {
            & docker tag $candidate $Image
            if ($LASTEXITCODE -ne 0) { throw "Could not tag $candidate as $Image" }
            return
        }
    }
    throw "All domestic pulls failed for $Image"
}

function Remove-TaskImage([string]$Image) {
    $tags = @($Image) + @($MirrorPrefixes | ForEach-Object { "$_/$Image" })
    foreach ($tag in $tags) {
        docker image inspect $tag *> $null
        if ($LASTEXITCODE -eq 0) {
            & docker image rm $tag | Out-Host
        }
    }
}

$tasks = @(Get-ChildItem -LiteralPath $TaskRoot -Directory | Sort-Object Name)
if ($tasks.Count -ne 89) { throw "Expected 89 tasks, found $($tasks.Count)" }

for ($index = 0; $index -lt $tasks.Count; $index++) {
    $task = $tasks[$index]
    $jobName = $task.Name
    $jobPath = Join-Path $JobsRoot $jobName
    $marker = Join-Path $jobPath ".coding-kid-complete"
    $image = Get-TaskImage $task.FullName
    if (Test-Path -LiteralPath $marker -PathType Leaf) {
        Write-Host "[$($index + 1)/$($tasks.Count)] complete: $($task.Name)"
        Remove-TaskImage $image
        continue
    }

    Write-Host "[$($index + 1)/$($tasks.Count)] starting: $($task.Name)"
    Ensure-TaskImage $image
    $completed = $false
    for ($retry = 0; $retry -le $MaximumInfrastructureRetries; $retry++) {
        if (Test-Path (Join-Path $jobPath "config.json")) {
            & $Harbor job resume --job-path $jobPath `
                --filter-error-type NonZeroAgentExitCodeError
        } else {
            & $Harbor run `
                --path $task.FullName `
                --agent-import-path coding_kid_harbor:CodingKidAgent `
                --model gpt-5.6-luna `
                --n-attempts $AttemptsPerTask `
                --n-concurrent 1 `
                --agent-setup-timeout-multiplier 5 `
                --no-force-build `
                --yes `
                --jobs-dir $JobsRoot `
                --job-name $jobName
        }
        $resultPath = Join-Path $jobPath "result.json"
        $result = if (Test-Path $resultPath) {
            Get-Content $resultPath -Raw | ConvertFrom-Json
        } else { $null }
        $scoredTrials = if ($result) {
            @($result.stats.evals.PSObject.Properties.Value |
                Measure-Object -Property n_trials -Sum).Sum
        } else { 0 }
        if (
            $LASTEXITCODE -eq 0 -and $result -and
            $result.stats.n_completed_trials -eq $AttemptsPerTask -and
            $scoredTrials -eq $AttemptsPerTask
        ) {
            $completed = $true
            break
        }
        Write-Warning "Harbor failed for $($task.Name), resume $($retry + 1)/$MaximumInfrastructureRetries"
    }
    if (-not $completed) { throw "Harbor repeatedly failed for $($task.Name)" }
    New-Item -ItemType File -Force -Path $marker | Out-Null
    Remove-TaskImage $image
}

Write-Host "All 89 Terminal-Bench 2.1 tasks completed."
