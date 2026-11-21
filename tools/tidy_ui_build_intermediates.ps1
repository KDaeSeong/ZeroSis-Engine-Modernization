[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string[]]$BuildId,
    [switch]$IncludeFailedBuilds,
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$buildRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot 'Build\UiWindowHost'))
$buildPrefix = $buildRoot.TrimEnd('\') + '\'
$referenced = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)

function Collect-ArtifactPaths($Node) {
    if ($null -eq $Node -or $Node -is [string] -or $Node.GetType().IsValueType) { return }
    if ($Node -is [Array]) { foreach ($child in $Node) { Collect-ArtifactPaths $child }; return }
    $pathProperty = $Node.PSObject.Properties['path']
    $hashProperty = $Node.PSObject.Properties['sha256']
    if ($null -ne $pathProperty -and $null -ne $hashProperty -and $pathProperty.Value) {
        [void]$referenced.Add([IO.Path]::GetFullPath([string]$pathProperty.Value))
    }
    foreach ($property in $Node.PSObject.Properties) { Collect-ArtifactPaths $property.Value }
}

function Digest([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Object-Identity([string]$Path) {
    $json = & 'C:\Python314\python.exe' -B -X utf8 -c 'import json,os,sys; s=os.stat(sys.argv[1],follow_symlinks=False); print(json.dumps(dict(device=str(s.st_dev),file_id=str(s.st_ino),bytes=s.st_size,mtime_ns=str(s.st_mtime_ns),links=s.st_nlink)))' $Path
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the final object file identity' }
    $identity = $json | ConvertFrom-Json
    if ($identity.file_id -eq '0' -or $identity.links -ne 1) {
        throw 'Final object has no stable identity or has another hardlink'
    }
    return $identity
}

function Same-ObjectIdentity($Before, $After) {
    return $Before.device -eq $After.device -and $Before.file_id -eq $After.file_id -and
        $Before.bytes -eq $After.bytes -and $Before.mtime_ns -eq $After.mtime_ns -and
        $Before.links -eq $After.links
}

function No-Active-Build {
    # A running Host loads sealed EXE/DLL inputs, never these unreferenced
    # compiler objects. Do not require closing a user's game to tidy them.
    # build_ui_window_host.py invokes cl/link directly. Reusable MSBuild
    # worker processes from other projects can remain idle indefinitely;
    # they are not evidence of an active UI Host compiler or linker.
    $active = @(Get-Process -Name cl,link,ninja -ErrorAction SilentlyContinue)
    if ($active.Count -gt 0) { throw 'Compiler/linker processes must finish before cleanup' }
}

function Validate-ObjectPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($buildPrefix,[StringComparison]::OrdinalIgnoreCase)) {
        throw "Intermediate escaped the private UI host build root: $full"
    }
    $relative = $full.Substring($buildPrefix.Length)
    if ($relative -notmatch '^\d{8}T\d{6}Z_[0-9a-f]{12}\\final\\(?:tu_00_host_main\\obj\\HostMain|tu_01_window\\obj\\BitmapWindow|tu_02_renderer\\obj\\BitmapRenderer|tu_03_world_renderer\\obj\\WorldViewRenderer|tu_04_terrain_renderer\\obj\\WorldTerrainRenderer)\.obj$') {
        throw "Unexpected intermediate path: $relative"
    }
    $item = Get-Item -LiteralPath $full
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Intermediate is not a regular owned file: $full"
    }
    $ancestor = $item.Directory
    while ($null -ne $ancestor -and $ancestor.FullName.StartsWith($buildPrefix,[StringComparison]::OrdinalIgnoreCase)) {
        if ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse point in intermediate path' }
        $ancestor = $ancestor.Parent
    }
    return $full
}

No-Active-Build
# Failed builds can leave final objects too. Check every retained hash record,
# rather than only the selected build report, before treating them as disposable.
$collectorPath = Join-Path $PSScriptRoot 'collect_intermediate_references.py'
$collectorHash = Digest $collectorPath
$indexText = & 'C:\Python314\python.exe' -B -X utf8 $collectorPath --root $projectRoot
if ($LASTEXITCODE -ne 0) { throw 'Preservation reference scan failed; no cleanup applied' }
$index = $indexText | ConvertFrom-Json -Depth 100
foreach ($path in $index.references) { [void]$referenced.Add([IO.Path]::GetFullPath($path)) }
$referenceDocuments = @($index.documents)
foreach ($document in Get-ChildItem -LiteralPath (Join-Path $projectRoot 'evidence') -Recurse -File |
         Where-Object { $_.Extension -in @('.csv','.manifest','.md','.txt') }) {
    $text = [IO.File]::ReadAllText($document.FullName)
    if ($text -notmatch '(?i)\.obj' -or $text -notmatch '[0-9a-fA-F]{64}') { continue }
    foreach ($line in ($text -split '\r?\n')) {
        if ($line -notmatch '[0-9a-fA-F]{64}') { continue }
        foreach ($match in [regex]::Matches($line,'(?i)[A-Z]:\\[^"\r\n,|]*\.obj\b')) {
            [void]$referenced.Add([IO.Path]::GetFullPath($match.Value))
        }
    }
    $referenceDocuments += @{path=$document.FullName;sha256=(Digest $document.FullName)}
}

$retained = @()
$buildStates = @()
$candidates = @()
$skipped = @()
$seenIds = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($id in $BuildId) {
    if ($id -notmatch '^\d{8}T\d{6}Z_[0-9a-f]{12}$' -or -not $seenIds.Add($id)) { throw 'Invalid or duplicate build ID' }
    $reportPath = Join-Path $projectRoot "evidence\ui_window_host\$id\build_result.json"
    $report = Get-Content -Raw -LiteralPath $reportPath | ConvertFrom-Json
    if ($report.build_id -ne $id) { throw "Build identity mismatch: $id" }
    if ($report.status -eq 'UI_WINDOW_HOST_CANDIDATE_BUILT') {
        if (-not $report.source_inputs_unchanged) { throw "Build inputs were not sealed: $id" }
        if ((Digest $report.executable.path) -ne $report.executable.sha256) { throw 'Retained executable changed' }
        $retained += @{path=$report.executable.path;sha256=$report.executable.sha256}
    } elseif ($IncludeFailedBuilds -and $report.status -eq 'UI_WINDOW_HOST_BUILD_FAILED') {
        if ($null -ne $report.executable) { throw "Failed build has an unclassified executable: $id" }
    } else {
        throw "Build is not sealed and successful, or an explicitly included failed build: $id"
    }
    Collect-ArtifactPaths $report
    $retained += @{path=$reportPath;sha256=(Digest $reportPath)}
    $buildStates += @{build_id=$id;status=$report.status}
    foreach ($tu in @('tu_00_host_main','tu_01_window','tu_02_renderer','tu_03_world_renderer','tu_04_terrain_renderer')) {
        $objectDirectory = Join-Path $buildRoot "$id\final\$tu\obj"
        if (-not (Test-Path -LiteralPath $objectDirectory -PathType Container)) { continue }
        foreach ($item in @(Get-ChildItem -LiteralPath $objectDirectory -File -Filter '*.obj')) {
            $full = Validate-ObjectPath $item.FullName
            if ($referenced.Contains($full)) { $skipped += $full; continue }
            $identity = Object-Identity $full
            $hash = Digest $full
            if (-not (Same-ObjectIdentity $identity (Object-Identity $full))) {
                throw 'Final object changed while creating its deletion record'
            }
            $candidates += @{path=$full;sha256=$hash;bytes=[long]$identity.bytes;identity=$identity}
        }
    }
}

$identifier = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '_' + [Guid]::NewGuid().ToString('N').Substring(0,12)
$evidence = Join-Path $projectRoot "evidence\build_tidy\$identifier"
[void][IO.Directory]::CreateDirectory($evidence)
$ledgerPath = Join-Path $evidence 'cleanup.json'
$ledger = [ordered]@{
    status='PLANNED';apply=[bool]$Apply;scope='unreferenced_final_UI_host_object_files_only';
    build_ids=$BuildId;script_sha256=(Digest $PSCommandPath);retained=$retained;
    include_failed_builds=[bool]$IncludeFailedBuilds;build_states=$buildStates;
    reference_collector=@{path=$collectorPath;sha256=$collectorHash};reference_documents=$referenceDocuments;
    deletion_plan_hashes_not_treated_as_retained_inputs=@($index.deletion_ledgers);
    candidates=$candidates;referenced_objects_skipped=$skipped;removed=@();removed_bytes=0;
    reference_documents_unchanged=$false;
    source_removed=$false;executable_removed=$false;runtime_or_save_removed=$false;
    frozen_inputs_removed=$false;stage_or_mods_changed=$false;error=$null
}
function Checkpoint {
    $ledger | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $ledgerPath -Encoding utf8NoBOM
}
Checkpoint
try {
    if ($Apply) {
        No-Active-Build
        if ((Digest $collectorPath) -ne $collectorHash) { throw 'Reference collector changed before cleanup' }
        foreach ($record in $referenceDocuments) {
            if ((Digest $record.path) -ne $record.sha256) { throw 'A preservation document changed before cleanup' }
        }
        foreach ($record in $retained) {
            if ((Digest $record.path) -ne $record.sha256) { throw 'A retained build proof or executable changed before cleanup' }
        }
        foreach ($record in $candidates) {
            $full = Validate-ObjectPath $record.path
            if ($referenced.Contains($full) -or
                -not (Same-ObjectIdentity $record.identity (Object-Identity $full)) -or
                (Digest $full) -ne $record.sha256 -or
                -not (Same-ObjectIdentity $record.identity (Object-Identity $full))) {
                throw 'Intermediate identity, timestamp, content, or protection changed after preflight'
            }
            Remove-Item -LiteralPath $full -Force
            if (Test-Path -LiteralPath $full) { throw 'Intermediate still exists after removal' }
            $ledger.removed += $record
            $ledger.removed_bytes += $record.bytes
            Checkpoint
        }
        foreach ($record in $retained) {
            if ((Digest $record.path) -ne $record.sha256) { throw 'Retained build proof or executable changed' }
        }
        $ledger.status = 'UNREFERENCED_INTERMEDIATES_REMOVED_RETAINED_INPUTS_UNCHANGED'
    } else { $ledger.status = 'PREVIEW_ONLY' }
    foreach ($record in $referenceDocuments) {
        if ((Digest $record.path) -ne $record.sha256) { throw 'A preservation document changed during cleanup' }
    }
    $ledger.reference_documents_unchanged=$true
} catch {
    $ledger.status = 'CLEANUP_FAILED';$ledger.error = $_.Exception.Message;Checkpoint;throw
}
Checkpoint
[ordered]@{status=$ledger.status;files_removed=$ledger.removed.Count;bytes_removed=$ledger.removed_bytes;
    report=$ledgerPath;report_sha256=(Digest $ledgerPath)} | ConvertTo-Json -Compress
