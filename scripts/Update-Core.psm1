Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return (-join ($sha.ComputeHash($stream) | ForEach-Object { $_.ToString('x2') })) }
    finally { $sha.Dispose(); $stream.Dispose() }
}

function Test-UpdateArchive([string]$ArchivePath, [string]$ExpectedVersion, [string]$Destination) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    if (Test-Path -LiteralPath $Destination) { Remove-Item -LiteralPath $Destination -Recurse -Force }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    $base = [IO.Path]::GetFullPath($Destination).TrimEnd('\') + '\'
    $zip = [IO.Compression.ZipFile]::OpenRead($ArchivePath)
    try {
        $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach ($entry in $zip.Entries) {
            $relative = $entry.FullName.Replace('/', '\')
            if (-not $relative.StartsWith('app\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Update package must contain only app/ files.' }
            $target = [IO.Path]::GetFullPath((Join-Path $Destination $relative))
            if (-not $target.StartsWith($base, [StringComparison]::OrdinalIgnoreCase)) { throw 'Update package contains an unsafe path.' }
            if (-not $seen.Add($target)) { throw 'Update package contains duplicate paths.' }
            if ([string]::IsNullOrEmpty($entry.Name)) { New-Item -ItemType Directory -Path $target -Force | Out-Null }
            else {
                New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $true)
            }
        }
    } finally { $zip.Dispose() }
    $app = Join-Path $Destination 'app'
    $versionFile = Join-Path $app 'version.json'
    if (-not (Test-Path -LiteralPath $versionFile)) { throw 'Update package is missing app/version.json.' }
    $version = [string]((Get-Content -LiteralPath $versionFile -Raw | ConvertFrom-Json).version)
    if ($version -ne $ExpectedVersion) { throw 'Update package version does not match the manifest.' }
    if (-not (Get-ChildItem -LiteralPath $app -Filter '*.exe' -File | Select-Object -First 1)) { throw 'Update package is missing its application executable.' }
}

function Queue-VerifiedUpdate([string]$Root, [string]$ArchivePath, [string]$ExpectedVersion, [string]$ExpectedSha256) {
    if ((Get-Sha256 $ArchivePath) -ne $ExpectedSha256.ToLowerInvariant()) { throw 'Update package SHA-256 does not match.' }
    $updater = Join-Path $Root 'updater'
    New-Item -ItemType Directory -Path $updater -Force | Out-Null
    $stage = Join-Path $updater ('validate-' + [guid]::NewGuid().ToString('N'))
    $pending = Join-Path $updater 'pending.zip'
    $metadata = Join-Path $updater 'pending.json'
    $tempZip = $pending + '.tmp'
    $tempJson = $metadata + '.tmp'
    try {
        Test-UpdateArchive -ArchivePath $ArchivePath -ExpectedVersion $ExpectedVersion -Destination $stage
        Copy-Item -LiteralPath $ArchivePath -Destination $tempZip -Force
        if ((Get-Sha256 $tempZip) -ne $ExpectedSha256.ToLowerInvariant()) { throw 'Staged package SHA-256 does not match.' }
        $json = @{version=$ExpectedVersion;sha256=$ExpectedSha256.ToLowerInvariant()} | ConvertTo-Json -Compress
        [IO.File]::WriteAllText($tempJson, $json, [Text.UTF8Encoding]::new($false))
        if (Test-Path -LiteralPath $pending) { Remove-Item -LiteralPath $pending -Force }
        if (Test-Path -LiteralPath $metadata) { Remove-Item -LiteralPath $metadata -Force }
        Move-Item -LiteralPath $tempZip -Destination $pending
        Move-Item -LiteralPath $tempJson -Destination $metadata
    } finally {
        Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $tempZip,$tempJson -Force -ErrorAction SilentlyContinue
    }
}

function Install-PendingUpdate([string]$Root) {
    $updater = Join-Path $Root 'updater'
    $pending = Join-Path $updater 'pending.zip'
    $metadata = Join-Path $updater 'pending.json'
    if (-not (Test-Path -LiteralPath $pending) -and -not (Test-Path -LiteralPath $metadata)) { return $false }
    if (-not (Test-Path -LiteralPath $pending) -or -not (Test-Path -LiteralPath $metadata)) { throw 'Pending update files are incomplete.' }
    $meta = Get-Content -LiteralPath $metadata -Raw | ConvertFrom-Json
    if ((Get-Sha256 $pending) -ne ([string]$meta.sha256).ToLowerInvariant()) { throw 'Pending update SHA-256 does not match.' }
    $stage = Join-Path $updater ('install-' + [guid]::NewGuid().ToString('N'))
    $newApp = Join-Path $stage 'app'
    $app = Join-Path $Root 'app'
    $backup = Join-Path $Root 'app.previous'
    try {
        Test-UpdateArchive -ArchivePath $pending -ExpectedVersion ([string]$meta.version) -Destination $stage
        if (Test-Path -LiteralPath $backup) { throw 'An existing app.previous backup must be reviewed before updating.' }
        if (Test-Path -LiteralPath $app) { [IO.Directory]::Move($app, $backup) }
        try {
            [IO.Directory]::Move($newApp, $app)
            $installed = [string]((Get-Content -LiteralPath (Join-Path $app 'version.json') -Raw | ConvertFrom-Json).version)
            if ($installed -ne [string]$meta.version) { throw 'Installed version verification failed.' }
            Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue
        } catch {
            if (-not (Test-Path -LiteralPath $app) -and (Test-Path -LiteralPath $backup)) { [IO.Directory]::Move($backup, $app) }
            throw
        }
        Remove-Item -LiteralPath $pending,$metadata -Force
        return $true
    } finally { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue }
}

Export-ModuleMember -Function Get-Sha256,Test-UpdateArchive,Queue-VerifiedUpdate,Install-PendingUpdate
