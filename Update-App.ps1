param(
    [Parameter(Mandatory = $true)]
    [string]$Root,
    # Alibaba Cloud OSS is the primary domestic endpoint. GitHub remains a
    # fallback below for users outside mainland networks or during OSS outages.
    [string]$ManifestUrl = "https://luotuoqiluotuozhaoma-download.oss-cn-beijing.aliyuncs.com/updates/latest.json"
)

$ErrorActionPreference = "Stop"
$Root = $Root.Trim().Trim('"')
if ([string]::IsNullOrWhiteSpace($Root)) { throw "Update root folder is empty" }
$Root = [IO.Path]::GetFullPath($Root)
$AppDir = Join-Path $Root "app"

# Some Windows PowerShell installations negotiate legacy TLS by default.
# GitHub requires modern TLS for its release endpoints.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Get-AppVersion([string]$VersionFile) {
    if (-not (Test-Path -LiteralPath $VersionFile)) { return [version]"0.0.0" }
    try {
        $value = (Get-Content -LiteralPath $VersionFile -Raw | ConvertFrom-Json).version
        return [version]([string]$value).TrimStart("v")
    } catch {
        return [version]"0.0.0"
    }
}

function Invoke-UpdateJson([string]$Url, [int]$MaxSeconds = 8) {
    # curl.exe handles redirects and transient network failures more reliably on
    # many Windows desktops. Keep the PowerShell request as a fallback.
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($null -ne $curl) {
        $raw = & $curl.Source -L --silent --show-error --connect-timeout 5 --max-time $MaxSeconds --retry 1 --retry-delay 1 $Url 2>$null
        if ($LASTEXITCODE -eq 0) {
            $text = $raw -join "`n"
            if (-not [string]::IsNullOrWhiteSpace($text)) {
                return $text | ConvertFrom-Json
            }
        }
        Write-Output "curl update request failed (exit code $LASTEXITCODE); trying fallback."
    }
    return Invoke-RestMethod -Uri $Url -TimeoutSec $MaxSeconds -Headers @{ "User-Agent" = "DouyinWorksExtractorUpdater" }
}

function Get-LatestManifest([string]$PrimaryUrl) {
    $primaryError = ""
    try {
        $manifest = Invoke-UpdateJson -Url $PrimaryUrl
        if ([string]::IsNullOrWhiteSpace($manifest.version) -or [string]::IsNullOrWhiteSpace($manifest.url) -or [string]::IsNullOrWhiteSpace($manifest.sha256)) {
            throw "Primary update manifest is incomplete"
        }
        return $manifest
    }
    catch {
        $primaryError = $_.Exception.Message
        Write-Output "Primary update request failed: $primaryError"
    }

    try {
        $release = Invoke-UpdateJson -Url "https://api.github.com/repos/nmrsz645-bit/douyin-works-extractor-desktop/releases/latest"
        $asset = @($release.assets | Where-Object { $_.name -eq "app.zip" }) | Select-Object -First 1
        $digest = [string]$asset.digest
        if ($null -eq $asset -or [string]::IsNullOrWhiteSpace($release.tag_name) -or -not $digest.StartsWith("sha256:")) {
            throw "GitHub release metadata is incomplete"
        }
        return [pscustomobject]@{
            version = [string]$release.tag_name
            url = [string]$asset.browser_download_url
            sha256 = $digest.Substring(7)
        }
    }
    catch {
        throw "Update check timed out or failed. Primary: $primaryError. Fallback: $($_.Exception.Message)"
    }
}

function Download-UpdatePackage([string]$Url, [string]$Destination) {
    Write-Output "Downloading update package..."

    # Do not use Start-BitsTransfer here.  On some computers the BITS service
    # can remain at "Connecting" indefinitely, which blocks the launcher and
    # never reaches the fallback. curl.exe has an explicit connection timeout
    # and is bundled with supported Windows 10/11 releases.
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($null -ne $curl) {
        & $curl.Source -L --fail --silent --show-error --connect-timeout 12 --max-time 1800 --retry 2 --retry-delay 2 --output $Destination $Url
        if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $Destination) -and ((Get-Item -LiteralPath $Destination).Length -gt 0)) {
            return
        }
        $curlExitCode = $LASTEXITCODE
        Remove-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue
        Write-Output "Direct download failed (curl exit code $curlExitCode); trying PowerShell fallback."
    }

    # Keep a generous transfer allowance, but a failed connection must not
    # leave a BITS job stuck in the user's system queue.
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
    $manifest = Get-LatestManifest -PrimaryUrl $ManifestUrl
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
