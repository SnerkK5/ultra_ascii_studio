from __future__ import annotations

import argparse
import hashlib
import shutil
from datetime import datetime
from pathlib import Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _copy_if_exists(src: Path, dst: Path) -> None:
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _latest_file(folder: Path, pattern: str) -> Path | None:
    items = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return items[0] if items else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble release bundle folder")
    parser.add_argument("--root", default=".", help="Project root")
    parser.add_argument("--out-root", default="release_bundle", help="Output root")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    out_root = root / args.out_root
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bundle = out_root / f"bundle_{ts}"

    installers_dir = bundle / "installers"
    backups_dir = bundle / "backup"
    source_dir = bundle / "source_essentials"
    manifests_dir = bundle / "manifests"

    installers_dir.mkdir(parents=True, exist_ok=True)
    backups_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)

    # Windows x64 artifacts from local build.
    _copy_if_exists(root / "dist" / "ASCIIStudio_Setup.exe", installers_dir / "windows" / "x64" / "ASCIIStudio_Setup_windows_x64.exe")
    _copy_if_exists(root / "dist" / "ASCIIStudio_WebBootstrap.exe", installers_dir / "windows" / "x64" / "ASCIIStudio_WebBootstrap_windows_x64.exe")
    _copy_if_exists(root / "release" / "ASCIIStudio_package.zip", installers_dir / "windows" / "x64" / "ASCIIStudio_package.zip")
    _copy_if_exists(root / "dist" / "ASCIIStudio.exe", installers_dir / "windows" / "x64" / "ASCIIStudio.exe")

    # If multi-platform installers already exist, include them.
    for platform in ("windows", "linux", "macos"):
        src = root / "release_bundle" / "installers" / platform
        if src.exists():
            dst = installers_dir / platform
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)

    # Placeholder notes for targets that were not built locally yet.
    placeholders = {
        installers_dir / "windows" / "x86" / "README.txt": (
            "x86 installer is not built in this local run.\n"
            "Run: ./packaging/build_windows.ps1 -Arch x86 (requires 32-bit Python + compatible deps).\n"
        ),
        installers_dir / "linux" / "x64" / "README.txt": (
            "Linux installer/package is not built in this local run.\n"
            "Run on Linux host: ./packaging/build_linux.sh x64\n"
        ),
        installers_dir / "macos" / "x64" / "README.txt": (
            "macOS x64 package is not built in this local run.\n"
            "Run on macOS host: ./packaging/build_macos.sh x64\n"
        ),
        installers_dir / "macos" / "arm64" / "README.txt": (
            "macOS arm64 package is not built in this local run.\n"
            "Run on macOS host: ./packaging/build_macos.sh arm64\n"
        ),
    }
    for path, txt in placeholders.items():
        if not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        if not any(path.parent.glob("*")):
            path.write_text(txt, encoding="utf-8")

    # Latest backup.
    latest_backup = _latest_file(root / "backups", "ultra_ascii_studio_backup_*.zip")
    if latest_backup:
        _copy_if_exists(latest_backup, backups_dir / latest_backup.name)

    # Essential source/build files.
    essentials = [
        "ascii_studio_qt.py",
        "advanced_editor.py",
        "render_worker.py",
        "core_utils.py",
        "settings_store.py",
        "export_progress.py",
        "mini_player.py",
        "online_installer_qt.py",
        "web_bootstrap_installer.py",
        "ASCIIStudio.spec",
        "ASCIIStudio_OnlineInstaller.spec",
        "ASCIIStudio_WebBootstrap.spec",
        "build_release.bat",
        "BUILD_AND_INSTALLER_INSTRUCTIONS_RU.md",
        "REMOTE_UPDATE_GUIDE_RU.md",
        "update_manifest.json",
        "update_manifest.example.json",
    ]
    for rel in essentials:
        _copy_if_exists(root / rel, source_dir / rel)

    for rel_dir in ("icons", "sounds", "Easter eggs", "packaging", ".github"):
        src = root / rel_dir
        if src.exists():
            dst = source_dir / rel_dir
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)

    # Checksums and file list.
    lines = []
    for f in sorted(bundle.rglob("*")):
        if f.is_file():
            rel = f.relative_to(bundle).as_posix()
            lines.append(f"{_sha256(f)}  {rel}")
    (manifests_dir / "SHA256SUMS.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    (manifests_dir / "bundle_path.txt").write_text(str(bundle), encoding="utf-8")

    print(bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
