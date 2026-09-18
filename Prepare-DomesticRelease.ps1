[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Version,

    [Parameter(Mandatory = $true)]
    [string]$UpdatePackage,

    [Parameter(Mandatory = $true)]
    [string]$FullPackage,

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

$normalizedVersion = Get-NormalizedVersion $Version
$updatePackage = [IO.Path]::GetFullPath($UpdatePackage)
$fullPackage = [IO.Path]::GetFullPath($FullPackage)
$outputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
$baseUrl = $OssBaseUrl.TrimEnd('/')

Assert-ZipFile $updatePackage 'Update package'
Assert-ZipFile $fullPackage 'Full package'
Assert-UpdatePackageLayout $updatePackage

$updatesDirectory = Join-Path $outputDirectory 'updates'
New-Item -ItemType Directory -Force -Path $updatesDirectory | Out-Null

$stagedUpdate = Join-Path $updatesDirectory 'app.zip'
$fullPackageName = "douyin-works-extractor-$normalizedVersion-windows-x64.zip"
$stagedFullPackage = Join-Path $updatesDirectory $fullPackageName
Copy-Item -LiteralPath $updatePackage -Destination $stagedUpdate -Force
Copy-Item -LiteralPath $fullPackage -Destination $stagedFullPackage -Force

$manifest = [ordered]@{
    version              = $normalizedVersion
    url                  = "$baseUrl/updates/app.zip"
    sha256               = (Get-FileHash -LiteralPath $stagedUpdate -Algorithm SHA256).Hash.ToLowerInvariant()
    fullPackageUrl       = "$baseUrl/updates/$fullPackageName"
    fullPackageSha256    = (Get-FileHash -LiteralPath $stagedFullPackage -Algorithm SHA256).Hash.ToLowerInvariant()
    fullPackageName      = $fullPackageName
}

$manifestPath = Join-Path $updatesDirectory 'latest.json'
$manifest | ConvertTo-Json -Compress | Set-Content -LiteralPath $manifestPath -Encoding utf8NoBOM

# A script tag can read this cross-origin file without a browser CORS rule.
# The download page uses it to display the same version and complete-package
# URL as the updater manifest.  Keep it alongside latest.json on OSS.
$websiteManifest = [ordered]@{
    version        = $normalizedVersion
    fullPackageUrl = $manifest.fullPackageUrl
}
$websiteManifestJson = $websiteManifest | ConvertTo-Json -Compress
$websiteManifestPath = Join-Path $updatesDirectory 'latest.js'
"window.DOUYIN_WORKS_EXTRACTOR_LATEST = $websiteManifestJson;" |
    Set-Content -LiteralPath $websiteManifestPath -Encoding utf8NoBOM

Write-Output "Release upload folder prepared: $outputDirectory"
Write-Output "Upload the contents of $updatesDirectory to OSS path updates/."
Write-Output "Publish latest.json and latest.js last, after both ZIP files have uploaded successfully."
Write-Output "Version: v$normalizedVersion"
