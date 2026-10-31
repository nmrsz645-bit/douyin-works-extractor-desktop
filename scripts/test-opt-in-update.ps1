$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'Update-Core.psm1') -Force
$work = Join-Path $env:TEMP ('DouyinOptInTest-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work | Out-Null
try {
    $root = Join-Path $work 'install'
    $app = Join-Path $root 'app'
    New-Item -ItemType Directory -Path $app -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $app 'version.json') -Value '{"version":"1.1.21"}' -NoNewline
    Set-Content -LiteralPath (Join-Path $app 'app.exe') -Value 'old-app' -NoNewline
    Set-Content -LiteralPath (Join-Path $work 'user-data.txt') -Value 'preserve' -NoNewline
    $packageRoot = Join-Path $work 'package'
    New-Item -ItemType Directory -Path (Join-Path $packageRoot 'app') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path (Join-Path $packageRoot 'app') 'version.json') -Value '{"version":"1.1.22"}' -NoNewline
    Set-Content -LiteralPath (Join-Path (Join-Path $packageRoot 'app') 'app.exe') -Value 'new-app' -NoNewline
    $zip = Join-Path $work 'update.zip'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::CreateFromDirectory($packageRoot, $zip)
    $hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    Queue-VerifiedUpdate -Root $root -ArchivePath $zip -ExpectedVersion '1.1.22' -ExpectedSha256 $hash
    if ((Get-Content -LiteralPath (Join-Path $app 'app.exe') -Raw) -ne 'old-app') { throw 'staging installed update in the same launch' }
    if (-not (Install-PendingUpdate -Root $root)) { throw 'next launch did not install pending update' }
    if ((Get-Content -LiteralPath (Join-Path $app 'app.exe') -Raw) -ne 'new-app') { throw 'new app was not installed' }
    if ((Get-Content -LiteralPath (Join-Path $work 'user-data.txt') -Raw) -ne 'preserve') { throw 'user data changed' }
    $bad = Join-Path $work 'bad.zip'
    Copy-Item -LiteralPath $zip -Destination $bad
    try { Queue-VerifiedUpdate -Root $root -ArchivePath $bad -ExpectedVersion '1.1.22' -ExpectedSha256 ('0' * 64); throw 'bad hash accepted' }
    catch { if ($_.Exception.Message -ne 'bad hash accepted' -and $_.Exception.Message -notmatch 'SHA-256') { throw } }
    if ((Get-Content -LiteralPath (Join-Path $app 'app.exe') -Raw) -ne 'new-app') { throw 'bad hash changed installed app' }
    'PASS: opt-in staging, next-launch install, hash rejection, user data preservation'
} finally {
    $tempRoot = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
    if (-not ([IO.Path]::GetFullPath($work).StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase))) { throw 'unsafe test cleanup path' }
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}
