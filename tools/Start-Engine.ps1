param(
    [ValidateSet('Continue', 'New', 'Load')][string]$Mode = 'Continue',
    [string]$Checkpoint,
    [switch]$EarlyAccess,
    [switch]$PlanOnly
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeIds = @('20261007T202612Z_d895c0fe84ab', '20261004T000710Z_796f1ea91c5e', '20261003T230735Z_2003f24507ce', '20261003T154510Z_b1af9e8eb764')
$earlyAccessRuntimeIds = @('20261012T121847Z_732a6d5f07ea', '20261010T065253Z_25bd25e6bca5', '20261010T035556Z_6d704df23b8d', '20261009T163702Z_0461db127034', '20261009T132430Z_a0a5dd8fd007', '20261009T123717Z_504abb2ccaf9')
if ($EarlyAccess) { $runtimeIds = $earlyAccessRuntimeIds + $runtimeIds }
$runtimeRoot = Join-Path $projectRoot 'Build\InteractiveGameRuntime'
$runtime = Join-Path $runtimeRoot $runtimeIds[0]
$mutex = New-Object System.Threading.Mutex($false, 'Local\ZeroSis_Engine_Manual_Play')
$ownsMutex = $false
$logDirectory = $null
function Get-EngineFileHash([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    $hash = [System.Security.Cryptography.SHA256]::Create()
    try { return [System.BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $hash.Dispose(); $stream.Dispose() }
}
function ConvertTo-EngineArgument([string]$Value) {
    $escaped = $Value -replace '(\\*)"', '$1$1\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    return '"' + $escaped + '"'
}
function Get-CheckpointBundleHash([string]$Path) {
    # Read only the bounded identity section for version routing. GameCore
    # still validates the entire archive checksum and every section on load.
    $reader = [System.IO.BinaryReader]::new([System.IO.File]::OpenRead($Path))
    $hash = [System.Security.Cryptography.SHA256]::Create()
    try {
        $header = $reader.ReadBytes(60)
        if ($header.Length -ne 60 -or
            [System.Text.Encoding]::ASCII.GetString($header, 0, 16) -cne "ZEROSIS_SAVE_V1`0" -or
            [System.BitConverter]::ToUInt32($header, 16) -ne 1 -or
            [System.BitConverter]::ToUInt32($header, 48) -ne 1 -or
            [System.BitConverter]::ToUInt32($header, 52) -ne 0) {
            throw 'This file is not a supported ZeroSis saved game.'
        }
        $size = [System.BitConverter]::ToUInt32($header, 56)
        if ($size -lt 1 -or $size -gt 16384) { throw 'Invalid saved-game engine identity size.' }
        $bundle = $reader.ReadBytes([int]$size)
        if ($bundle.Length -ne $size) { throw 'Truncated saved-game engine identity.' }
        return [System.BitConverter]::ToString($hash.ComputeHash($bundle)).Replace('-', '').ToLowerInvariant()
    } finally { $hash.Dispose(); $reader.Dispose() }
}
try {
    if (-not $PlanOnly) {
        try { $ownsMutex = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $ownsMutex = $true }
    }
    if (-not $PlanOnly -and -not $ownsMutex) {
        Add-Type -AssemblyName System.Windows.Forms
        [void][System.Windows.Forms.MessageBox]::Show('The engine is already running. Use the open ZeroSis window.', "ZeroSis' Civilization")
        return
    }
    $effectiveMode = $Mode
    $checkpoint = $Checkpoint
    if ($Mode -eq 'New') {
        if ($checkpoint) { throw 'A new game cannot also specify a saved game.' }
    } else {
        if ($Mode -eq 'Continue') {
            if ($checkpoint) { throw 'Use Load to open a specified saved game.' }
            # These runtimes were prepared for manual play. Smoke-test
            # runtimes are deliberately absent from this continuation list.
            # Continue the latest user save from either Early Access release;
            # Load still routes historical user saves to their exact engine.
            $continuationIds = if ($EarlyAccess) { $earlyAccessRuntimeIds } else { $runtimeIds }
            $savedGames = foreach ($id in $continuationIds) {
                $sessionRoot = Join-Path (Join-Path $runtimeRoot $id) 'sessions'
                if (Test-Path -LiteralPath $sessionRoot) {
                    Get-ChildItem -LiteralPath $sessionRoot -Filter 'play-save-*-turn-*.zssave' -File -Recurse
                }
            }
            $latest = $savedGames | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
            if ($latest) { $checkpoint = $latest.FullName } else { $effectiveMode = 'New' }
        } elseif (-not $checkpoint) {
            if ($PlanOnly) { throw 'Load planning requires an explicit checkpoint.' }
            Add-Type -AssemblyName System.Windows.Forms
            $picker = New-Object System.Windows.Forms.OpenFileDialog
            $picker.Title = "ZeroSis' Civilization - Open saved game"
            $picker.Filter = 'ZeroSis saves (*.zssave)|*.zssave'
            $picker.InitialDirectory = Join-Path $runtime 'sessions'
            try {
                if ($picker.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { return }
                $checkpoint = $picker.FileName
            } finally { $picker.Dispose() }
        }
    }
    if ($effectiveMode -ne 'New') {
        $checkpoint = [System.IO.Path]::GetFullPath($checkpoint)
        $bundleHash = Get-CheckpointBundleHash $checkpoint
        $matchingRuntimes = @(foreach ($id in $runtimeIds) {
            $candidate = Join-Path $runtimeRoot $id
            if ((Get-EngineFileHash (Join-Path $candidate 'bundle.manifest')) -eq $bundleHash) { $candidate }
        })
        if ($matchingRuntimes.Count -eq 0) { throw 'The engine version used by this saved game is not in the retained play versions.' }
        $runtime = $matchingRuntimes[0]
    }
    $runtimeId = Split-Path -Leaf $runtime
    $requestPath = Join-Path $projectRoot ('evidence\interactive_game\' + $runtimeId + '\request.json')
    $request = Get-Content -LiteralPath $requestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($request.run_id -ne $runtimeId -or $request.cwd -ne $runtime -or $request.smoke) {
        throw 'The selected runtime is not a prepared manual-play version.'
    }
    foreach ($reference in @($request.launcher_control_metadata.play, $request.launcher_control_metadata.resume)) {
        if ((Get-EngineFileHash $reference.path) -ne $reference.sha256) {
            throw 'The prepared game launcher changed. Recreate the launcher before playing.'
        }
    }
    $launcher = Join-Path $runtime $(if ($effectiveMode -eq 'New') { 'Play.ps1' } else { 'Resume.ps1' })
    if ($PlanOnly) {
        [ordered]@{requested_mode=$Mode;mode=$effectiveMode;early_access=[bool]$EarlyAccess;runtime=$runtime;checkpoint=$checkpoint;
            host_sha256=(Get-EngineFileHash (Join-Path $runtime 'ZeroSisHost_x64.exe'));
            launcher=$launcher;smoke_inputs=$false;total_play_timeout_seconds=0} | ConvertTo-Json -Depth 4
        return
    }
    $launchId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '_' + [guid]::NewGuid().ToString('N').Substring(0, 12)
    $logDirectory = Join-Path $projectRoot ('evidence\manual_play\' + $launchId)
    [void][System.IO.Directory]::CreateDirectory($logDirectory)
    $startRecord = [ordered]@{
        status = 'LAUNCHING'; mode = $effectiveMode; requested_mode = $Mode; launcher_pid = $PID
        runtime = $runtime; checkpoint = $checkpoint; started_utc = [DateTime]::UtcNow.ToString('o')
        total_play_timeout_seconds = 0; smoke_inputs = $false
        full_gameplay_verified = $false; installed_game_changed = $false
    }
    $recordPath = Join-Path $logDirectory 'launch.json'
    $startRecord | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $recordPath -Encoding UTF8
    $outLog = Join-Path $logDirectory 'stdout.log'
    $errLog = Join-Path $logDirectory 'stderr.log'
    # Windows PowerShell can turn redirected native stderr (including the
    # driver's informational PID line) into a terminating NativeCommandError.
    # Give the native process file handles directly; its exit code/report own
    # failure detection, while both streams keep draining throughout play.
    $command = @($request.command)
    $nativeArguments = New-Object 'System.Collections.Generic.List[string]'
    for ($index = 1; $index -lt $command.Count; $index++) {
        $argument = [string]$command[$index]
        if ($argument -eq '--checkpoint') { $index++; continue }
        $nativeArguments.Add($argument)
        if ($argument -eq '--mode') {
            $index++
            $nativeArguments.Add($(if ($effectiveMode -eq 'New') { 'play' } else { 'play-load' }))
        } elseif ($argument -eq '--timeout') {
            $index++; $nativeArguments.Add('0')
        } elseif ($argument -eq '--report') {
            $index++; $nativeArguments.Add((Join-Path $logDirectory 'driver_result.json'))
        }
    }
    if ($effectiveMode -ne 'New') { $nativeArguments.Add('--checkpoint'); $nativeArguments.Add($checkpoint) }
    $quotedArguments = ($nativeArguments | ForEach-Object { ConvertTo-EngineArgument $_ }) -join ' '
    $env:PYTHONDONTWRITEBYTECODE = '1'
    # Do not reconstruct the inherited environment in legacy Start-Process:
    # this desktop can supply both Path and PATH, which its dictionary rejects.
    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = [string]$command[0]
    $processInfo.Arguments = $quotedArguments
    $processInfo.WorkingDirectory = $runtime
    $processInfo.UseShellExecute = $false
    $processInfo.CreateNoWindow = $true
    $processInfo.RedirectStandardOutput = $true
    $processInfo.RedirectStandardError = $true
    # Manual play must never inherit developer fixture flags. The sealed
    # driver restores its explicitly requested TopPanel option on the child.
    foreach ($key in @($processInfo.EnvironmentVariables.Keys)) {
        if ([string]$key -like 'ZEROSIS_PLAY_*') { $processInfo.EnvironmentVariables.Remove([string]$key) }
    }
    $processInfo.EnvironmentVariables['ZEROSIS_UI_POLICY_INFO'] = '1'
    $playProcess = New-Object System.Diagnostics.Process
    $playProcess.StartInfo = $processInfo
    $outStream = [System.IO.File]::Create($outLog)
    $errStream = [System.IO.File]::Create($errLog)
    if (-not $playProcess.Start()) { throw 'Could not start the game driver.' }
    $outCopy = $playProcess.StandardOutput.BaseStream.CopyToAsync($outStream)
    $errCopy = $playProcess.StandardError.BaseStream.CopyToAsync($errStream)
    $startRecord.status = 'DRIVER_RUNNING'
    $startRecord.driver_pid = $playProcess.Id
    $startRecord | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $recordPath -Encoding UTF8
    try {
        $playProcess.WaitForExit()
        $outCopy.GetAwaiter().GetResult()
        $errCopy.GetAwaiter().GetResult()
    } finally { $outStream.Dispose(); $errStream.Dispose() }
    if ($playProcess.ExitCode -ne 0) { throw "Engine exited with code $($playProcess.ExitCode). Logs: $logDirectory" }
    $startRecord.status = 'CLOSED'
    $startRecord.closed_utc = [DateTime]::UtcNow.ToString('o')
    $startRecord | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $recordPath -Encoding UTF8
} catch {
    if ($PlanOnly) { throw }
    Add-Type -AssemblyName System.Windows.Forms
    $message = $_.Exception.Message
    if ($logDirectory) { $message | Set-Content -LiteralPath (Join-Path $logDirectory 'launcher-error.txt') -Encoding UTF8 }
    if ($startRecord -and $recordPath) {
        $startRecord.status = 'FAILED'
        $startRecord.error = $message
        $startRecord | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $recordPath -Encoding UTF8
    }
    [void][System.Windows.Forms.MessageBox]::Show($message, "ZeroSis' Civilization - launch failed")
    exit 1
} finally {
    if ($ownsMutex) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
