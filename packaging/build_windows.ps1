param(
    [ValidateSet("x64", "x86")]
    [string]$Arch = "x64",
    [string]$OutRoot = "release_bundle",
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

$pyBits = [int](& $PythonExe -c "import struct; print(struct.calcsize('P')*8)")
if ($Arch -eq "x64" -and $pyBits -ne 64) {
    throw "x64 build requested, but current Python is ${pyBits}-bit."
}
if ($Arch -eq "x86" -and $pyBits -ne 32) {
    throw "x86 build requested, but current Python is ${pyBits}-bit. Use 32-bit Python."
}

$buildRoot = Join-Path $root ".build_out\windows-$Arch"
$distPath = Join-Path $buildRoot "dist"
$workPath = Join-Path $buildRoot "build"
$artifactDir = Join-Path $root "$OutRoot\installers\windows\$Arch"

if (Test-Path $buildRoot) { Remove-Item $buildRoot -Recurse -Force }
New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $root "release") -Force | Out-Null

& $PythonExe -m PyInstaller --noconfirm --clean ASCIIStudio.spec --distpath "$distPath" --workpath "$workPath"

$warnPath = Join-Path $workPath "ASCIIStudio\warn-ASCIIStudio.txt"
if (Test-Path $warnPath) {
    $warnText = Get-Content $warnPath -Raw
    if ($warnText -match "missing module named '?PySide6") {
        throw "Build is not usable: PySide6 modules are missing for this Python/arch. See $warnPath"
    }
}

@'
from pathlib import Path
import zipfile

root = Path(r"__ROOT__")
dist_path = Path(r"__DIST__")
artifact = Path(r"__ART__")
app_dir = dist_path / "ASCIIStudio"
release_zip = root / "release" / "ASCIIStudio_package.zip"
portable_zip = artifact / "ASCIIStudio_windows___ARCH___portable.zip"

for p in (release_zip, portable_zip):
    if p.exists():
        p.unlink()

def pack(src_dir: Path, dst_zip: Path, level: int = 6):
    with zipfile.ZipFile(dst_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=level) as zf:
        for f in src_dir.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(src_dir))

pack(app_dir, release_zip, level=6)
pack(app_dir, portable_zip, level=6)
print(f"Packed: {release_zip}")
print(f"Packed: {portable_zip}")
'@.Replace("__ROOT__", $root).Replace("__DIST__", $distPath).Replace("__ART__", $artifactDir).Replace("__ARCH__", $Arch) | & $PythonExe -

& $PythonExe -m PyInstaller --noconfirm --clean ASCIIStudio_OnlineInstaller.spec --distpath "$distPath" --workpath "$workPath"
Copy-Item (Join-Path $distPath "ASCIIStudio_Setup.exe") (Join-Path $artifactDir "ASCIIStudio_Setup_windows_$Arch.exe") -Force

& $PythonExe -m PyInstaller --noconfirm --clean ASCIIStudio_WebBootstrap.spec --distpath "$distPath" --workpath "$workPath"
Copy-Item (Join-Path $distPath "ASCIIStudio_WebBootstrap.exe") (Join-Path $artifactDir "ASCIIStudio_WebBootstrap_windows_$Arch.exe") -Force

@'
from pathlib import Path
import hashlib

artifact = Path(r"__ART__")
out = artifact / "SHA256SUMS.txt"
lines = []
for f in sorted(artifact.glob("*")):
    if not f.is_file() or f.name == out.name:
        continue
    h = hashlib.sha256()
    with f.open("rb") as fd:
        for chunk in iter(lambda: fd.read(1024 * 1024), b""):
            h.update(chunk)
    lines.append(f"{h.hexdigest()}  {f.name}")
out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
print(out)
'@.Replace("__ART__", $artifactDir) | & $PythonExe -

Write-Host "Done. Artifacts: $artifactDir"
