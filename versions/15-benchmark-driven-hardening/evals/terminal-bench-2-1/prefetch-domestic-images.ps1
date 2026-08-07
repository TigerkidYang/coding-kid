param(
    [string]$TaskRoot = "$PSScriptRoot/task-inspection/full/terminal-bench-2-1",
    [string[]]$MirrorPrefixes = @(
        "dockerproxy.net",
        "docker.1ms.run",
        "docker.m.daocloud.io",
        "docker.xuanyuan.me",
        "docker.1panel.live"
    ),
    [double]$MinimumFreeGB = 20
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $TaskRoot -PathType Container)) {
    throw "Task root does not exist: $TaskRoot"
}

$images = @(
    Get-ChildItem -LiteralPath $TaskRoot -Directory |
        ForEach-Object {
            $taskFile = Join-Path $_.FullName "task.toml"
            $line = Get-Content -LiteralPath $taskFile |
                Where-Object { $_ -match '^docker_image\s*=\s*"(.+)"' } |
                Select-Object -First 1
            if ($line -notmatch '^docker_image\s*=\s*"(.+)"') {
                throw "No docker_image in $taskFile"
            }
            $Matches[1]
        } |
        Sort-Object -Unique
)

if ($images.Count -ne 89) {
    throw "Expected 89 unique task images, found $($images.Count)"
}

for ($index = 0; $index -lt $images.Count; $index++) {
    $image = $images[$index]
    if ($image -match '^[^/]+\.[^/]+/') {
        throw "Non-Docker-Hub image needs an explicit domestic route: $image"
    }

    docker image inspect $image *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[$($index + 1)/$($images.Count)] cached $image"
        continue
    }

    $drive = Get-PSDrive -Name C
    $freeGB = $drive.Free / 1GB
    if ($freeGB -lt $MinimumFreeGB) {
        throw "Only $([math]::Round($freeGB, 1)) GB remains before pulling $image"
    }

    $domesticImage = $null
    foreach ($prefix in $MirrorPrefixes) {
        $candidate = "$prefix/$image"
        Write-Host "[$($index + 1)/$($images.Count)] pulling $candidate"
        docker pull $candidate
        if ($LASTEXITCODE -eq 0) {
            $domesticImage = $candidate
            break
        }
    }
    if (-not $domesticImage) {
        throw "All domestic pulls failed for $image"
    }
    docker tag $domesticImage $image
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to tag $image"
    }

    $domesticID = docker image inspect $domesticImage --format '{{.Id}}'
    $officialID = docker image inspect $image --format '{{.Id}}'
    if ($domesticID -ne $officialID) {
        throw "Image ID mismatch after tagging $image"
    }
}

Write-Host "All 89 Terminal-Bench 2.1 images are available under official tags."
