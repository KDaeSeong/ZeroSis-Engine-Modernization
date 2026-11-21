param(
    [string]$File
)
$ErrorActionPreference = 'Stop'
$sdkProjectRoot = Split-Path -Parent $PSScriptRoot
$sdkEditorExe = Join-Path $env:LOCALAPPDATA 'Programs\Microsoft VS Code\Code.exe'
$sdkWorkspace = Join-Path $sdkProjectRoot 'SDK-Fast-Edit.code-workspace'
$sdkEditorProfile = Join-Path ([System.IO.Path]::GetTempPath()) 'ZeroSis-SDK-Fast-Edit'
if (-not (Test-Path -LiteralPath $sdkEditorExe -PathType Leaf)) {
    throw 'Installed VS Code was not found. No editor or extension will be installed automatically.'
}
$sdkEditorArguments = @('--new-window', '--disable-extensions', '--user-data-dir', ('"{0}"' -f $sdkEditorProfile), ('"{0}"' -f $sdkWorkspace))
if ($File) {
    $sdkRequestedFile = [System.IO.Path]::GetFullPath($File)
    if (-not $sdkRequestedFile.StartsWith($sdkProjectRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase) -or
        -not (Test-Path -LiteralPath $sdkRequestedFile -PathType Leaf)) {
        throw 'The requested file must exist inside this SDK project.'
    }
    $sdkEditorArguments += ('"{0}"' -f $sdkRequestedFile)
}
# An isolated local profile avoids global preference writes and OneDrive cache I/O.
Start-Process -FilePath $sdkEditorExe -ArgumentList $sdkEditorArguments -WindowStyle Hidden
