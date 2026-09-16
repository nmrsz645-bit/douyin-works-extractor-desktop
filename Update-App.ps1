param(
    [Parameter(Mandatory = $true)]
    [string]$Root,
    [string]$ManifestUrl = "https://github.com/nmrsz645-bit/douyin-works-extractor-desktop/releases/latest/download/latest.json"
)

$ErrorActionPreference = "Stop"
$Root = [IO.Path]::GetFullPath($Root)
$AppDir = Join-Path $Root "app"

function Get-AppVersion([string]$VersionFile) {
    if (-not (Test-Path -LiteralPath $VersionFile)) { return [version]"0.0.0" }
    try {
        $value = (Get-Content -LiteralPath $VersionFile -Raw | ConvertFrom-Json).version
        return [version]([string]$value).TrimStart("v")
    } catch {
        return [version]"0.0.0"
    }
}

try {
    $localVersion = Get-AppVersion (Join-Path $AppDir "version.json")
    $manifest = Invoke-RestMethod -Uri $ManifestUrl -TimeoutSec 12
    $remoteVersion = [version]([string]$manifest.version).TrimStart("v")
    if ($remoteVersion -le $localVersion -or [string]::IsNullOrWhiteSpace($manifest.url) -or [string]::IsNullOrWhiteSpace($manifest.sha256)) {
        Write-Output "No update available (installed: $localVersion)."
        exit 0
    }

    $zip = Join-Path $Root ".app-update.zip"
    $staging = Join-Path $Root ".app-update-staging"
    $backup = Join-Path $Root ".app-backup"
    Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue
    Invoke-WebRequest -Uri $manifest.url -OutFile $zip -UseBasicParsing -TimeoutSec 180
    $actualHash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne ([string]$manifest.sha256).ToLowerInvariant()) { throw "Update package verification failed" }
    Expand-Archive -LiteralPath $zip -DestinationPath $staging -Force
    $newApp = Join-Path $staging "app"
    if (-not (Test-Path -LiteralPath $newApp)) { throw "Invalid update package structure" }
    Move-Item -LiteralPath $AppDir -Destination $backup -Force
    try {
        Move-Item -LiteralPath $newApp -Destination $AppDir -Force
        Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue
    } catch {
        if (-not (Test-Path -LiteralPath $AppDir) -and (Test-Path -LiteralPath $backup)) {
            Move-Item -LiteralPath $backup -Destination $AppDir -Force
        }
        throw
    }
    Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
    Write-Output "Updated application from $localVersion to $remoteVersion."
} catch {
    # The CMD launcher starts the installed application after this script exits.
    # Keep an actionable record instead of silently hiding update failures.
    Write-Error "Update check failed: $($_.Exception.Message)"
}
