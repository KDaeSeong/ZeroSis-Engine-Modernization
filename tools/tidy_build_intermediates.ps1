[CmdletBinding()]
param([switch]$Apply)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$buildRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot 'Build'))
$buildPrefix = $buildRoot.TrimEnd('\') + '\'
$extensions = @('.obj','.o','.pch','.ipch','.ilk','.tlog','.pyc')
# Preserve the SDK incremental cache and reusable original/candidate baselines.
$preservedGroups = @('SDKIncremental','SDK_x64','SDK_Reference','LuaBorrowed','ICU44','RuntimeInputCache','UiWindowHost')
$references = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$referenceDocuments = @()
$deletionLedgers = @()

function Add-Reference([string]$Path) {
    if (-not $Path -or -not [IO.Path]::IsPathFullyQualified($Path)) { return }
    $full = [IO.Path]::GetFullPath($Path)
    if ($full.StartsWith($buildPrefix,[StringComparison]::OrdinalIgnoreCase)) {
        [void]$references.Add($full)
    }
}
function Digest([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Valid-File([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($buildPrefix,[StringComparison]::OrdinalIgnoreCase)) { throw 'Cleanup path escaped the private Build root' }
    $item = Get-Item -LiteralPath $full
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Cleanup target is not a regular owned file' }
    $ancestor = $item.Directory
    while ($null -ne $ancestor -and $ancestor.FullName.StartsWith($buildRoot,[StringComparison]::OrdinalIgnoreCase)) {
        if ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse point inside cleanup path' }
        if ($ancestor.FullName -eq $buildRoot) { break }
        $ancestor = $ancestor.Parent
    }
    return $full
}
function No-Active-Compiler {
    $active = @(Get-Process -Name cl,link,ZeroSisHost_x64 -ErrorAction SilentlyContinue)
    if ($active.Count -gt 0) { throw ('Compiler/linker/Host processes must finish before cleanup: ' + (($active | ForEach-Object { $_.ProcessName + ':' + $_.Id }) -join ', ')) }
}

No-Active-Compiler
# Use a stdlib reader for the large JSON evidence tree. PowerShell retains
# ownership of path validation, hash checks and every actual deletion.
# Malformed matching JSON fails closed instead of hiding possible references.
$collectorPath = Join-Path $PSScriptRoot 'collect_intermediate_references.py'
$pythonExe = 'C:\Python314\python.exe'
$collectorHash = Digest $collectorPath
$indexText = & $pythonExe -B -X utf8 $collectorPath --root $projectRoot
if ($LASTEXITCODE -ne 0) { throw 'Preservation reference scan failed; no cleanup applied' }
$index = $indexText | ConvertFrom-Json -Depth 100
foreach ($path in $index.references) { Add-Reference $path }
$referenceDocuments = @($index.documents)
$deletionLedgers = @($index.deletion_ledgers)
foreach ($document in Get-ChildItem -LiteralPath (Join-Path $projectRoot 'evidence') -Recurse -File |
         Where-Object { $_.Extension -in @('.csv','.manifest','.md','.txt') }) {
    $text = [IO.File]::ReadAllText($document.FullName)
    if ($text -notmatch '(?i)\.(obj|o|pch|ipch|ilk|tlog|pyc)' -or $text -notmatch '[0-9a-fA-F]{64}') { continue }
    foreach ($line in ($text -split '\r?\n')) {
        if ($line -notmatch '[0-9a-fA-F]{64}') { continue }
        foreach ($match in [regex]::Matches($line,'(?i)[A-Z]:\\[^"\r\n,|]*\.(?:obj|o|pch|ipch|ilk|tlog|pyc)\b')) {
            Add-Reference $match.Value
        }
    }
    $referenceDocuments += @{path=$document.FullName;sha256=(Digest $document.FullName)}
}

$candidates = @()
$referenced = @()
$frozen = @()
$preserved = @()
foreach ($item in Get-ChildItem -LiteralPath $buildRoot -Recurse -File) {
    if ($item.Extension.ToLowerInvariant() -notin $extensions) { continue }
    $relative = $item.FullName.Substring($buildPrefix.Length)
    $group = ($relative -split '\\',2)[0]
    if ($group -in $preservedGroups) { $preserved += $item.FullName; continue }
    if ($relative -match '(?i)(^|\\)(frozen|frozen_inputs|source_inputs|sealed_inputs|include_roots)(\\|$)') {
        $frozen += $item.FullName; continue
    }
    if ($references.Contains($item.FullName)) { $referenced += $item.FullName; continue }
    $full = Valid-File $item.FullName
    $candidates += @{path=$full;sha256=(Digest $full);bytes=[long]$item.Length;group=$group}
}

$identifier = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '_' + [Guid]::NewGuid().ToString('N').Substring(0,12)
$evidence = Join-Path $projectRoot "evidence\intermediate_tidy\$identifier"
[void][IO.Directory]::CreateDirectory($evidence)
$ledgerPath = Join-Path $evidence 'cleanup.json'
$ledger = [ordered]@{
    status='PREVIEW_ONLY';apply=[bool]$Apply;scope='unreferenced_nonfrozen_compiler_intermediates_in_private_Build';
    script_sha256=(Digest $PSCommandPath);reference_documents=$referenceDocuments;
    reference_collector=@{path=$collectorPath;sha256=$collectorHash};
    deletion_plan_hashes_not_treated_as_retained_inputs=$deletionLedgers;
    preserved_groups=$preservedGroups;preserved_cache_or_baseline_count=$preserved.Count;
    frozen_inputs_skipped_count=$frozen.Count;hash_referenced_skipped_count=$referenced.Count;
    candidates=$candidates;removed=@();removed_bytes=0;reference_documents_unchanged=$false;
    executable_or_library_removed=$false;source_removed=$false;runtime_or_save_removed=$false;
    stage_or_mods_changed=$false;error=$null
}
function Checkpoint { $ledger | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath $ledgerPath -Encoding utf8NoBOM }
Checkpoint
try {
    if ($Apply) {
        No-Active-Compiler
        if ((Digest $collectorPath) -ne $collectorHash) { throw 'Reference collector changed before cleanup' }
        foreach ($record in $referenceDocuments) {
            if ((Digest $record.path) -ne $record.sha256) { throw 'A preservation document changed during cleanup planning' }
        }
        foreach ($record in $candidates) {
            $full = Valid-File $record.path
            if ($references.Contains($full) -or (Digest $full) -ne $record.sha256) { throw 'An intermediate changed or became protected before removal' }
            Remove-Item -LiteralPath $full -Force
            if (Test-Path -LiteralPath $full) { throw 'Intermediate still exists after removal' }
            $ledger.removed += $record;$ledger.removed_bytes += $record.bytes
            Checkpoint
        }
        $ledger.status='UNREFERENCED_INTERMEDIATES_REMOVED'
    }
    foreach ($record in $referenceDocuments) {
        if ((Digest $record.path) -ne $record.sha256) { throw 'A preservation document changed during cleanup' }
    }
    $ledger.reference_documents_unchanged=$true
} catch {
    $ledger.status='CLEANUP_FAILED';$ledger.error=$_.Exception.Message;Checkpoint;throw
}
Checkpoint
[long]$candidateBytes = 0
foreach ($record in $candidates) { $candidateBytes += [long]$record.bytes }
[ordered]@{status=$ledger.status;candidate_count=$candidates.Count;
    candidate_bytes=$candidateBytes;
    files_removed=$ledger.removed.Count;bytes_removed=$ledger.removed_bytes;
    protected_count=$referenced.Count;report=$ledgerPath;report_sha256=(Digest $ledgerPath)} | ConvertTo-Json -Compress
