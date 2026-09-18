[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Version,

    [Parameter(Mandatory = $true)]
    [string]$UpdatePackage,

    [Parameter(Mandatory = $true)]
    [string]$FullPackage,

    [string]$UpdatePackageName,

    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'release-upload'),

    [string]$OssBaseUrl = 'https://luotuoqiluotuozhaoma-download.oss-cn-beijing.aliyuncs.com'
)

$ErrorActionPreference = 'Stop'

function Get-NormalizedVersion([string]$Value) {
    $normalized = $Value.Trim().TrimStart('v', 'V')
    try {
        [void][version]$normalized
        return $normalized
    } catch {
        throw "Invalid version: $Value"
    }
}

function Assert-ZipFile([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label does not exist: $Path"
    }
    if ([IO.Path]::GetExtension($Path) -ne '.zip') {
        throw "$Label must be a .zip file: $Path"
    }
    if ((Get-Item -LiteralPath $Path).Length -le 0) {
        throw "$Label is empty: $Path"
    }
}

function Get-Sha256([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        return (-join ($hasher.ComputeHash($stream) | ForEach-Object { $_.ToString('x2') }))
    } finally {
        $hasher.Dispose()
        $stream.Dispose()
    }
}

function Assert-UpdatePackageLayout([string]$Path) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $hasVersionFile = $archive.Entries | Where-Object { $_.FullName -ieq 'app/version.json' } | Select-Object -First 1
        if ($null -eq $hasVersionFile) {
            throw "Update package must contain app/version.json: $Path"
        }
    } finally {
        $archive.Dispose()
    }
}

function Get-SafeZipName([string]$Name, [string]$Label) {
    if ([string]::IsNullOrWhiteSpace($Name) -or $Name -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*\.zip$') {
        throw "$Label must be a ZIP file name without a directory: $Name"
    }
    return $Name
}

$normalizedVersion = Get-NormalizedVersion $Version
$updatePackage = [IO.Path]::GetFullPath($UpdatePackage)
$fullPackage = [IO.Path]::GetFullPath($FullPackage)
$outputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
$baseUrl = $OssBaseUrl.TrimEnd('/')

if ([string]::IsNullOrWhiteSpace($UpdatePackageName)) {
    $UpdatePackageName = "douyin-works-extractor-update-$normalizedVersion.zip"
}
$UpdatePackageName = Get-SafeZipName $UpdatePackageName 'UpdatePackageName'

Assert-ZipFile $updatePackage 'Update package'
Assert-ZipFile $fullPackage 'Full package'
Assert-UpdatePackageLayout $updatePackage

$updatesDirectory = Join-Path $outputDirectory 'updates'
New-Item -ItemType Directory -Force -Path $updatesDirectory | Out-Null

$stagedUpdate = Join-Path $updatesDirectory $UpdatePackageName
$fullPackageName = "douyin-works-extractor-$normalizedVersion-windows-x64.zip"
$stagedFullPackage = Join-Path $updatesDirectory $fullPackageName
Copy-Item -LiteralPath $updatePackage -Destination $stagedUpdate -Force
Copy-Item -LiteralPath $fullPackage -Destination $stagedFullPackage -Force

$manifest = [ordered]@{
    version              = $normalizedVersion
    url                  = "$baseUrl/updates/$UpdatePackageName"
    sha256               = Get-Sha256 $stagedUpdate
    fullPackageUrl       = "$baseUrl/updates/$fullPackageName"
    fullPackageSha256    = Get-Sha256 $stagedFullPackage
    fullPackageName      = $fullPackageName
}

$manifestPath = Join-Path $updatesDirectory 'latest.json'
# Windows PowerShell 5.1 does not support Set-Content -Encoding utf8NoBOM.
# Write UTF-8 without BOM through .NET so local and GitHub Actions builds match.
$utf8NoBom = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Compress), $utf8NoBom)

# A script tag can read this cross-origin file without a browser CORS rule.
# The download page uses it to display the same version and complete-package
# URL as the updater manifest.  Keep it alongside latest.json on OSS.
$websiteManifest = [ordered]@{
    version        = $normalizedVersion
    fullPackageUrl = $manifest.fullPackageUrl
}
$websiteManifestJson = $websiteManifest | ConvertTo-Json -Compress
$websiteManifestPath = Join-Path $updatesDirectory 'latest.js'
[IO.File]::WriteAllText(
    $websiteManifestPath,
    "window.DOUYIN_WORKS_EXTRACTOR_LATEST = $websiteManifestJson;",
    $utf8NoBom
)

Write-Output "Release upload folder prepared: $outputDirectory"
Write-Output "Upload the contents of $updatesDirectory to OSS path updates/."
Write-Output "Publish latest.json and latest.js last, after both ZIP files have uploaded successfully."
Write-Output "Version: v$normalizedVersion"
