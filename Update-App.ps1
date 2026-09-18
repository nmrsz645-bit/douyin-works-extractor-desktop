param(
    [Parameter(Mandatory = $true)]
    [string]$Root,
    # Alibaba Cloud OSS is the only production update endpoint.
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

function Get-Sha256([string]$Path) {
    # Some managed Windows PowerShell installations load a restricted utility
    # module, in which Get-FileHash is unexpectedly unavailable. Use the .NET
    # implementation bundled with Windows instead, so the updater remains
    # self-contained on those computers.
    $stream = [IO.File]::OpenRead($Path)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = $hasher.ComputeHash($stream)
        return (-join ($bytes | ForEach-Object { $_.ToString('x2') }))
    } finally {
        $hasher.Dispose()
        $stream.Dispose()
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
    try {
        $manifest = Invoke-UpdateJson -Url $PrimaryUrl
        if ([string]::IsNullOrWhiteSpace($manifest.version) -or [string]::IsNullOrWhiteSpace($manifest.url) -or [string]::IsNullOrWhiteSpace($manifest.sha256)) {
            throw "Domestic OSS update manifest is incomplete"
        }
        return $manifest
    }
    catch {
        throw "Domestic OSS update check failed: $($_.Exception.Message)"
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

function Move-UpdateDirectory([string]$Source, [string]$Destination) {
    # Directory.Move is an atomic rename on the same volume. If the program is
    # installed on another drive, use a copy/delete fallback so recovery still
    # works instead of failing only because %TEMP% is on C:.
    try {
        [IO.Directory]::Move($Source, $Destination)
        return
    }
    catch {
        Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
        Remove-Item -LiteralPath $Source -Recurse -Force
    }
}

function Expand-UpdatePackage([string]$ArchivePath, [string]$Destination) {
    # Expand-Archive in Windows PowerShell 5.1 can fail on Playwright's deep
    # Chromium paths. The destination is intentionally short and ZipFile avoids
    # that cmdlet's path handling.
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::ExtractToDirectory($ArchivePath, $Destination)
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
    # The bundled Chromium directory has long nested paths. Keep every update
    # work path short so older Windows PowerShell can extract it reliably.
    $workRoot = Join-Path ([IO.Path]::GetTempPath()) ("dwe-" + [guid]::NewGuid().ToString("N"))
    $staging = Join-Path $workRoot "s"
    $backup = Join-Path $workRoot "b"
    Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $workRoot -Force | Out-Null
    Download-UpdatePackage -Url $manifest.url -Destination $zip
    $actualHash = Get-Sha256 $zip
    if ($actualHash -ne ([string]$manifest.sha256).ToLowerInvariant()) { throw "Update package verification failed" }
    Expand-UpdatePackage -ArchivePath $zip -Destination $staging
    $newApp = Join-Path $staging "app"
    if (-not (Test-Path -LiteralPath $newApp)) { throw "Invalid update package structure" }
    Move-UpdateDirectory -Source $AppDir -Destination $backup
    try {
        Move-UpdateDirectory -Source $newApp -Destination $AppDir
        Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue
    } catch {
        if (-not (Test-Path -LiteralPath $AppDir) -and (Test-Path -LiteralPath $backup)) {
            Move-UpdateDirectory -Source $backup -Destination $AppDir
        }
        throw
    }
    Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $workRoot -Recurse -Force -ErrorAction SilentlyContinue
    Write-Output "Updated application from $localVersion to $remoteVersion."
} catch {
    # The CMD launcher starts the installed application after this script exits.
    # Keep an actionable record instead of silently hiding update failures.
    Write-Error "Update check failed: $($_.Exception.Message)"
}
