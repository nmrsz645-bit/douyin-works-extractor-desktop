param(
    [Parameter(Mandatory = $true)]
    [string]$Root,
    [string]$ManifestUrl = "https://github.com/nmrsz645-bit/douyin-works-extractor-desktop/releases/latest/download/latest.json"
)

$ErrorActionPreference = "Stop"
$Root = $Root.Trim().Trim('"')
if ([string]::IsNullOrWhiteSpace($Root)) { throw "Update root folder is empty" }
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

function Download-UpdatePackage([string]$Url, [string]$Destination) {
    Write-Output "Downloading update package..."

    # BITS is more tolerant of slow or temporarily interrupted connections than
    # Invoke-WebRequest, and is available on normal Windows desktop systems.
    try {
        if (Get-Command Start-BitsTransfer -ErrorAction SilentlyContinue) {
            Start-BitsTransfer -Source $Url -Destination $Destination -DisplayName "Douyin Works Extractor update" -ErrorAction Stop
            return
        }
    }
    catch {
        Write-Output "BITS download unavailable; falling back to direct download."
    }

    # Keep a generous fallback limit for machines where the BITS service is disabled.
    Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing -TimeoutSec 1800
}

function Confirm-Update([version]$CurrentVersion, [version]$NewVersion) {
    try {
        Add-Type -AssemblyName PresentationFramework -ErrorAction Stop
        $message = "A new version v$NewVersion is available (current: v$CurrentVersion).`n`nThe full update package is about 477 MB. Update now?"
        $result = [System.Windows.MessageBox]::Show(
            $message,
            "Douyin Works Extractor - Update Available",
            [System.Windows.MessageBoxButton]::YesNo,
            [System.Windows.MessageBoxImage]::Information
        )
        return $result -eq [System.Windows.MessageBoxResult]::Yes
    }
    catch {
        # A desktop Windows release normally has PresentationFramework. If it is
        # unavailable, retain automatic update behavior instead of blocking launch.
        return $true
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
    if (-not (Confirm-Update -CurrentVersion $localVersion -NewVersion $remoteVersion)) {
        Write-Output "Update skipped by user."
        exit 0
    }

    $zip = Join-Path $Root ".app-update.zip"
    $staging = Join-Path $Root ".app-update-staging"
    $backup = Join-Path $Root ".app-backup"
    Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue
    Download-UpdatePackage -Url $manifest.url -Destination $zip
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
