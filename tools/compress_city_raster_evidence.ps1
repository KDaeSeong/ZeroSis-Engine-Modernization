[CmdletBinding()]
param([Parameter(Mandatory=$true)][string[]]$RunId)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class CityRasterStorageNative {
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern uint GetCompressedFileSizeW(string file, out uint high);
}
'@
function StoredBytes([string]$Path) {
    [uint32]$high=0
    $low=[CityRasterStorageNative]::GetCompressedFileSizeW($Path,[ref]$high)
    if ($low -eq [uint32]::MaxValue -and [Runtime.InteropServices.Marshal]::GetLastWin32Error() -ne 0) {
        throw "Cannot inspect compressed storage: $Path"
    }
    return ([uint64]$high*4294967296)+[uint64]$low
}
function Digest([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
$rows=[Collections.Generic.List[object]]::new()
foreach($id in $RunId) {
    if($id -notmatch '^\d{8}T\d{6}Z_[0-9a-f]{12}$') { throw 'Invalid completed run ID' }
    $root=[IO.Path]::GetFullPath((Join-Path $project "Build\InteractiveGameRuntime\$id\sessions"))
    $prefix=$root.TrimEnd('\')+'\'
    $resultPath=Join-Path $project "evidence\interactive_game\$id\result.json"
    $result=Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
    if($result.run_id -cne $id -or $result.status -notlike '*_PASS' -or $result.failures.Count -ne 0) { throw 'Only completed passing evidence is eligible' }
    foreach($record in $result.generated_files) {
        $path=[IO.Path]::GetFullPath([string]$record.path)
        if([IO.Path]::GetFileName($path) -notmatch '^cityraster_[0-9a-f]{24}\.dds$') { continue }
        if(-not $path.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) { throw 'Raster escaped its exact completed run' }
        $item=Get-Item -LiteralPath $path -Force
        if($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Raster must be an ordinary file' }
        $before=Digest $path
        if($before -cne $record.sha256) { throw 'Raster differs from its retained evidence hash' }
        $row=[ordered]@{path=$path;sha256=$before;logical_bytes=$item.Length;stored_before=(StoredBytes $path);stored_after=$null;unchanged=$false}
        # NTFS transparent compression preserves every path and byte. No
        # referenced artifact is deleted, replaced, or rewritten by this script.
        $nativeOutput=& "$env:SystemRoot\System32\compact.exe" /C /I /Q $path 2>&1
        if($LASTEXITCODE -ne 0) { throw "Raster compression failed: $nativeOutput" }
        $row.stored_after=StoredBytes $path
        $row.unchanged=(Digest $path) -ceq $before
        if(-not $row.unchanged) { throw 'Raster content changed during transparent compression' }
        $rows.Add([pscustomobject]$row)
    }
}
if($rows.Count -eq 0) { throw 'No eligible retained raster evidence found' }
$stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')+'_'+[guid]::NewGuid().ToString('N').Substring(0,12)
$folder=Join-Path $project "evidence\build_tidy\$stamp"
[void](New-Item -ItemType Directory -Path $folder)
$report=Join-Path $folder 'raster_storage.json'
$beforeTotal=($rows | Measure-Object stored_before -Sum).Sum
$afterTotal=($rows | Measure-Object stored_after -Sum).Sum
$result=[ordered]@{status='RETAINED_CITY_RASTER_NTFS_COMPRESSION_PASS';run_ids=$RunId;files=$rows.ToArray();stored_before=$beforeTotal;stored_after=$afterTotal;stored_reduction=$beforeTotal-$afterTotal;all_paths_and_hashes_preserved=$true;volume_free_space_increase_measured=$false;game_install_or_saves_modified=$false}
[IO.File]::WriteAllText($report,($result | ConvertTo-Json -Depth 8)+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))
@{status=$result.status;files=$rows.Count;stored_reduction=$result.stored_reduction;report=$report;sha256=(Digest $report)} | ConvertTo-Json -Compress
