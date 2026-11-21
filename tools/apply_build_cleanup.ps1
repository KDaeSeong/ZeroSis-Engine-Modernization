# This script defaults to verification. Apply only after explicit user approval
# of the exact plan hash; its presence is not itself evidence of authorization.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$PlanPath,
    [ValidateSet('Validate', 'Apply')][string]$Mode = 'Validate',
    [string]$ApprovedPlanSha256 = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectDirectory = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
$buildDirectory = [IO.Path]::GetFullPath((Join-Path $projectDirectory 'Build')).TrimEnd('\')
$buildPrefix = $buildDirectory + '\'
$planFile = (Resolve-Path -LiteralPath $PlanPath).ProviderPath
$planHash = (Get-FileHash -LiteralPath $planFile -Algorithm SHA256).Hash.ToLowerInvariant()
$plan = Get-Content -LiteralPath $planFile -Raw | ConvertFrom-Json

function Assert-OrdinaryPath([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Reparse point is outside the cleanup contract: $Path"
    }
    return $item
}

function Assert-WithinBuild([string]$Path) {
    $fullPath = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    if (-not $fullPath.StartsWith($buildPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Cleanup path escaped the project Build directory: $Path"
    }
    return $fullPath
}

function Assert-Artifact($Record) {
    $item = Get-Item -LiteralPath $Record.path -Force
    if ($item.PSIsContainer -or (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Record.sha256) {
        throw "An input changed after the cleanup plan was prepared: $($Record.path)"
    }
}

function Get-BuildArtifacts($Value) {
    if ($null -eq $Value -or $Value -is [string] -or $Value -is [ValueType]) { return }
    if ($Value -is [array]) {
        foreach ($entry in $Value) { Get-BuildArtifacts $entry }
        return
    }
    $names = @($Value.PSObject.Properties | ForEach-Object { $_.Name })
    if ($names -contains 'path' -and $names -contains 'sha256' -and $Value.path -is [string]) {
        if ($Value.path.StartsWith($buildPrefix, [StringComparison]::OrdinalIgnoreCase)) { $Value }
    }
    foreach ($property in $Value.PSObject.Properties) { Get-BuildArtifacts $property.Value }
}

function Assert-NoActiveBuild {
    $active = @()
    foreach ($process in Get-Process) {
        if ($process.ProcessName -in @('cl', 'link', 'MSBuild', 'ninja')) {
            $active += "$($process.Id):$($process.ProcessName)"
            continue
        }
        try { $processPath = $process.Path } catch { $processPath = $null }
        if ($processPath -and $processPath.StartsWith($buildPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            $active += "$($process.Id):$processPath"
        }
    }
    if ($active.Count -ne 0) { throw ('Build processes must finish before cleanup: ' + ($active -join ', ')) }
}

function Assert-Inventory($Record) {
    $target = Assert-WithinBuild $Record.path
    $rootItem = Assert-OrdinaryPath $target
    if (-not $rootItem.PSIsContainer) { throw "Cleanup target is not a directory: $target" }
    $prefix = $target + '\'
    $expected = [Collections.Generic.Dictionary[string, object]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($entry in $Record.files) {
        if ([IO.Path]::IsPathRooted($entry.relative_path) -or $entry.relative_path.Contains(':')) {
            throw 'Cleanup manifest contains a rooted path or alternate stream'
        }
        $fullFile = [IO.Path]::GetFullPath((Join-Path $target $entry.relative_path))
        if (-not $fullFile.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Manifest file escaped its target' }
        $expected.Add($fullFile, $entry)
    }
    [long]$bytes = 0
    $found = 0
    foreach ($item in Get-ChildItem -LiteralPath $target -Force -Recurse) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Reparse point inside cleanup target: $($item.FullName)" }
        if ($item.PSIsContainer) { continue }
        if (-not $expected.ContainsKey($item.FullName)) { throw "Unplanned file appeared: $($item.FullName)" }
        $entry = $expected[$item.FullName]
        if ($item.Length -ne $entry.bytes -or (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256) {
            throw "Cleanup file changed: $($item.FullName)"
        }
        $bytes += $item.Length
        $found++
    }
    if ($found -ne $expected.Count -or $found -ne $Record.file_count -or $bytes -ne $Record.bytes) {
        throw "Cleanup inventory differs: $target"
    }
}

if ($plan.status -ne 'PROPOSED_NOT_DELETED' -or $plan.project_root -ne $projectDirectory -or $plan.build_root -ne $buildDirectory) {
    throw 'Cleanup plan does not identify this project and Build directory'
}
if ($Mode -eq 'Apply' -and ($ApprovedPlanSha256 -notmatch '^[0-9a-f]{64}$' -or $ApprovedPlanSha256 -ne $planHash)) {
    throw 'Apply requires the exact explicitly approved cleanup plan hash'
}
$null = Assert-OrdinaryPath $buildDirectory
$null = Assert-OrdinaryPath (Join-Path $buildDirectory 'SDK_x64')
$null = Assert-OrdinaryPath (Join-Path $buildDirectory 'NewGameRuntime')
Assert-Artifact $plan.planner
Assert-NoActiveBuild

$targets = @($plan.targets)
$seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
[long]$plannedBytes = 0
$plannedFiles = 0
foreach ($target in $targets) {
    $targetPath = Assert-WithinBuild $target.path
    if (-not $seen.Add($targetPath)) { throw 'Duplicate cleanup target' }
    $relative = $targetPath.Substring($buildPrefix.Length)
    if ($target.group -eq 'historical_sdk_attempts') {
        if ($relative -notmatch '^SDK_x64\\attempt_(00[1-9]|0[12][0-9]|03[0-6])$') { throw "Unexpected SDK cleanup target: $relative" }
    } elseif ($target.group -eq 'failed_isolated_runtime_copies') {
        if ($relative -notmatch '^NewGameRuntime\\\d{8}T\d{6}Z_[0-9a-f]{12}$') { throw "Unexpected runtime cleanup target: $relative" }
        Assert-Artifact $target.execution_result
        $result = Get-Content -LiteralPath $target.execution_result.path -Raw | ConvertFrom-Json
        if ($result.status -notin @('ISOLATED_NEW_GAME_CANDIDATE_FAILED', 'ISOLATED_FIRST_TURN_ENTRY_FAILED')) {
            throw 'A runtime cleanup candidate is no longer a failed run'
        }
    } else { throw 'Unknown cleanup target group' }
    $plannedBytes += $target.bytes
    $plannedFiles += $target.file_count
}
if ($plannedBytes -ne $plan.total_bytes -or $targets.Count -ne 65 -or $plannedFiles -ne 5736) {
    throw 'The reviewed cleanup scope differs from 65 directories / 5736 files'
}

$protected = [Collections.Generic.Dictionary[string, object]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($record in $plan.current_dependency_reports) {
    Assert-Artifact $record
    if ([IO.Path]::GetExtension($record.path) -eq '.json') {
        $data = Get-Content -LiteralPath $record.path -Raw | ConvertFrom-Json
        foreach ($entry in Get-BuildArtifacts $data) { $protected[$entry.path] = $entry }
    }
}
foreach ($entry in $protected.Values) {
    foreach ($target in $targets) {
        if ($entry.path -eq $target.path -or $entry.path.StartsWith($target.path + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Current build input overlaps a cleanup target'
        }
    }
    Assert-Artifact $entry
}
foreach ($record in $plan.kept) {
    $null = Assert-OrdinaryPath $record.path
    if (@($record.PSObject.Properties | ForEach-Object { $_.Name }) -contains 'files') { Assert-Inventory $record }
}
foreach ($path in $plan.unclassified_preserved) { $null = Assert-OrdinaryPath $path }
foreach ($target in $targets) { Assert-Inventory $target }
Assert-NoActiveBuild

$driveRoot = [IO.Path]::GetPathRoot($buildDirectory)
$beforeFree = [IO.DriveInfo]::new($driveRoot).AvailableFreeSpace
$report = [ordered]@{
    status = 'VALIDATED_NOT_DELETED'
    captured_at_utc = [DateTime]::UtcNow.ToString('o')
    plan_path = $planFile
    plan_sha256 = $planHash
    mode = $Mode
    target_directories = $targets.Count
    planned_files = $plannedFiles
    planned_bytes = $plannedBytes
    protected_build_artifacts_checked = $protected.Count
    active_build_processes = 0
    deleted_files = 0
    deleted_bytes = [long]0
    removed_directories = @()
    before_free_bytes = $beforeFree
    after_free_bytes = $beforeFree
}
$reportName = 'validation-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ') + '.json'
if ($Mode -eq 'Apply') {
    $reportName = 'deletion-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ') + '.json'
    try {
        foreach ($target in $targets) {
            Assert-NoActiveBuild
            Assert-Inventory $target
            # Delete only the approved file list. New arrivals cannot be swept
            # up by recursive deletion; non-empty directories are left intact.
            foreach ($entry in $target.files) {
                $filePath = Assert-WithinBuild (Join-Path $target.path $entry.relative_path)
                $item = Assert-OrdinaryPath $filePath
                if ($item.PSIsContainer -or $item.Length -ne $entry.bytes) { throw 'Cleanup file identity changed before deletion' }
                Remove-Item -LiteralPath $filePath -Force
                $report.deleted_files++
                $report.deleted_bytes += $entry.bytes
            }
            $directories = @(Get-ChildItem -LiteralPath $target.path -Directory -Force -Recurse | Sort-Object { $_.FullName.Length } -Descending)
            foreach ($directory in $directories) {
                $null = Assert-WithinBuild $directory.FullName
                $null = Assert-OrdinaryPath $directory.FullName
                [IO.Directory]::Delete($directory.FullName, $false)
            }
            $null = Assert-WithinBuild $target.path
            [IO.Directory]::Delete($target.path, $false)
            $report.removed_directories += $target.path
        }
        foreach ($entry in $protected.Values) { Assert-Artifact $entry }
        foreach ($record in $plan.kept) {
            if (@($record.PSObject.Properties | ForEach-Object { $_.Name }) -contains 'files') { Assert-Inventory $record }
        }
        $report.status = 'BUILD_CLEANUP_COMPLETED'
    } catch {
        $report.status = 'BUILD_CLEANUP_PARTIAL_FAILURE'
        $report.error = $_.Exception.Message
        throw
    } finally {
        $report.after_free_bytes = [IO.DriveInfo]::new($driveRoot).AvailableFreeSpace
        $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path ([IO.Path]::GetDirectoryName($planFile)) $reportName) -Encoding utf8
    }
} else {
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path ([IO.Path]::GetDirectoryName($planFile)) $reportName) -Encoding utf8
}
$report | ConvertTo-Json -Depth 8 -Compress
