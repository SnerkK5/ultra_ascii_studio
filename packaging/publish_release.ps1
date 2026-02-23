param(
    [string]$Tag = "",
    [string]$Title = "",
    [string]$NotesFile = "",
    [switch]$Draft,
    [switch]$Prerelease,
    [switch]$NoLatest
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

function Resolve-AppVersionTag {
    $src = Join-Path $root "ascii_studio_qt.py"
    if (Test-Path $src) {
        $text = Get-Content $src -Raw
        $m = [regex]::Match($text, 'APP_VERSION\s*=\s*"([^"]+)"')
        if ($m.Success) { return "v$($m.Groups[1].Value)" }
    }
    return "v1.0.0"
}

if ([string]::IsNullOrWhiteSpace($Tag)) {
    $Tag = Resolve-AppVersionTag
}
if ([string]::IsNullOrWhiteSpace($Title)) {
    $Title = "ASCII Studio $Tag"
}

function Resolve-GhExe {
    $cmd = Get-Command gh -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return $cmd.Source }
    $fallback = "C:\Program Files\GitHub CLI\gh.exe"
    if (Test-Path -LiteralPath $fallback) { return $fallback }
    return $null
}

$ghExe = Resolve-GhExe
if (-not $ghExe) {
    throw "GitHub CLI is not installed. Install with: winget install --id GitHub.cli -e"
}

function Invoke-Gh {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    & $ghExe @Args
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        throw "gh command failed ($code): gh $($Args -join ' ')"
    }
}

$hasEnvToken = -not [string]::IsNullOrWhiteSpace($env:GH_TOKEN)
if ($hasEnvToken) {
    Write-Host "Using GH_TOKEN from environment."
} else {
    try {
        Invoke-Gh auth status | Out-Null
    } catch {
        throw "GitHub CLI is not authenticated. Use 'gh auth login' or set GH_TOKEN."
    }
}

$assetCandidates = @(
    "release_bundle/installers/windows/x64/ASCIIStudio_Setup_windows_x64.exe",
    "release_bundle/installers/windows/x64/ASCIIStudio_WebBootstrap_windows_x64.exe",
    "release_bundle/installers/windows/x64/ASCIIStudio_windows_x64_portable.zip",
    "release_bundle/installers/windows/x64/SHA256SUMS.txt",
    "release_bundle/installers/windows/x86/ASCIIStudio_Setup_windows_x86.exe",
    "release_bundle/installers/windows/x86/ASCIIStudio_WebBootstrap_windows_x86.exe",
    "release_bundle/installers/windows/x86/ASCIIStudio_windows_x86_portable.zip",
    "release_bundle/installers/windows/x86/SHA256SUMS.txt",
    "release_bundle/installers/linux/x64/ASCIIStudio_linux_x64_portable.tar.gz",
    "release_bundle/installers/linux/x64/SHA256SUMS.txt",
    "release_bundle/installers/macos/x64/ASCIIStudio_macos_x64_portable.zip",
    "release_bundle/installers/macos/x64/SHA256SUMS.txt",
    "release_bundle/installers/macos/arm64/ASCIIStudio_macos_arm64_portable.zip",
    "release_bundle/installers/macos/arm64/SHA256SUMS.txt",
    "release_bundle/installers/android/universal/ASCIIStudio_Android_universal_debug.apk",
    "release_bundle/installers/android/universal/ASCIIStudio_Android_universal_release_unsigned.apk",
    "release_bundle/installers/android/universal/SHA256SUMS.txt"
)

$assets = @()
foreach ($rel in $assetCandidates) {
    $full = Join-Path $root $rel
    if (Test-Path -LiteralPath $full) { $assets += $full }
}

if ($assets.Count -eq 0) {
    throw "No release assets found in release_bundle/installers/**. Build artifacts first."
}

$notesPath = $NotesFile
if ([string]::IsNullOrWhiteSpace($notesPath)) {
    $tmp = Join-Path $env:TEMP ("ascii_studio_release_notes_" + [Guid]::NewGuid().ToString("N") + ".md")
    $list = ($assets | ForEach-Object { "- " + (Split-Path $_ -Leaf) }) -join [Environment]::NewLine
    @"
# ASCII Studio $Tag

Automated release publish.

## Included assets
$list
"@ | Set-Content $tmp -Encoding UTF8
    $notesPath = $tmp
}

$exists = $false
try {
    Invoke-Gh release view $Tag --json tagName --jq .tagName | Out-Null
    $exists = $true
} catch {
    $exists = $false
}

if ($exists) {
    Write-Host "Release $Tag exists -> uploading/updating assets..."
    Invoke-Gh release upload $Tag @assets --clobber
} else {
    Write-Host "Creating release $Tag..."
    $args = @("release", "create", $Tag) + $assets + @("--title", $Title, "--notes-file", $notesPath)
    if ($Draft) { $args += "--draft" }
    if ($Prerelease) { $args += "--prerelease" }
    Invoke-Gh @args
}

if (-not $NoLatest -and -not $Prerelease) {
    try { Invoke-Gh release edit $Tag --latest } catch { Write-Warning "Could not set latest flag automatically." }
}

Write-Host "Done. Release published: $Tag"
