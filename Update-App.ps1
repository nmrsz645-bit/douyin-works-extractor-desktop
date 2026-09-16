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

function Start-Application {
    $exe = Get-ChildItem -LiteralPath $AppDir -Filter "*.exe" -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $exe) {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show("Application files are incomplete. Please download the full package again.", "Douyin Works Extractor") | Out-Null
        exit 1
    }
    Start-Process -FilePath $exe.FullName -WorkingDirectory $AppDir
}

try {
    $localVersion = Get-AppVersion (Join-Path $AppDir "version.json")
    $manifest = Invoke-RestMethod -Uri $ManifestUrl -TimeoutSec 12
    $remoteVersion = [version]([string]$manifest.version).TrimStart("v")
    if ($remoteVersion -le $localVersion -or [string]::IsNullOrWhiteSpace($manifest.url) -or [string]::IsNullOrWhiteSpace($manifest.sha256)) {
        Start-Application
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
} catch {
    # When offline or an update fails, start the installed version instead.
}

Start-Application
