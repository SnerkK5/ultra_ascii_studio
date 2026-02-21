# ASCII Studio

ASCII Studio is a desktop app for converting images, GIFs, and videos into high-quality ASCII visuals.
It includes real-time preview, advanced style controls, timeline/editor tools, node workflows, presets, themes, and built-in update delivery.

## Downloads

Latest stable downloads (always point to the newest release):

- Windows Setup (x64): [ASCIIStudio_Setup_windows_x64.exe](https://github.com/SnerkK5/ultra_ascii_studio/releases/latest/download/ASCIIStudio_Setup_windows_x64.exe)
- Windows Web Installer (x64): [ASCIIStudio_WebBootstrap_windows_x64.exe](https://github.com/SnerkK5/ultra_ascii_studio/releases/latest/download/ASCIIStudio_WebBootstrap_windows_x64.exe)
- Windows Portable (x64): [ASCIIStudio_windows_x64_portable.zip](https://github.com/SnerkK5/ultra_ascii_studio/releases/latest/download/ASCIIStudio_windows_x64_portable.zip)
- Linux Portable (x64): [ASCIIStudio_linux_x64_portable.tar.gz](https://github.com/SnerkK5/ultra_ascii_studio/releases/latest/download/ASCIIStudio_linux_x64_portable.tar.gz)
- macOS Portable (Intel x64): [ASCIIStudio_macos_x64_portable.zip](https://github.com/SnerkK5/ultra_ascii_studio/releases/latest/download/ASCIIStudio_macos_x64_portable.zip)
- macOS Portable (Apple Silicon arm64): [ASCIIStudio_macos_arm64_portable.zip](https://github.com/SnerkK5/ultra_ascii_studio/releases/latest/download/ASCIIStudio_macos_arm64_portable.zip)

Release page:
- [All releases](https://github.com/SnerkK5/ultra_ascii_studio/releases)

## Core Features

- Image, GIF, and video import
- Real-time ASCII preview (toggleable)
- Export to PNG, GIF, MP4, and TXT
- Presets (save/load)
- Pro Tools effects and stylization controls
- Embedded editor with:
  - text/media layers
  - crop and mask tools
  - timeline controls
  - audio import and source-audio reuse
  - node workspace (video/audio/data chain)
- Watermark support with custom watermark text
- Built-in themes + custom theme mode
- Multi-language UI (EN/RU/ZH)
- Built-in update check/install flow

## Build

Quick local build (Windows):

```powershell
build_release.bat
```

Platform scripts:

- Windows: `packaging/build_windows.ps1`
- Linux: `packaging/build_linux.sh`
- macOS: `packaging/build_macos.sh`

CI workflow:

- `.github/workflows/build-installers-matrix.yml`

## One-Command Release Publish (GitHub CLI)

Use the prepared script:

```powershell
./packaging/publish_release.ps1
```

Optional custom tag:

```powershell
./packaging/publish_release.ps1 -Tag v1.2.0
```

What it does:
- detects release assets in `release_bundle/installers/**`
- creates release if missing, or uploads with overwrite if release exists
- can auto-mark release as latest

## Update Manifest

App reads `update_feed_url` and expects manifest like:

```json
{
  "latest_version": "1.2.1",
  "installer_url": "https://your-domain/releases/ASCIIStudio_Setup_windows_x64.exe",
  "notes": "Bug fixes and performance improvements"
}
```

Required keys:
- `latest_version`
- `installer_url` (or `url`)

## Project Files

- `ascii_studio_qt.py` - main app window and UX
- `render_worker.py` - background rendering pipeline
- `export_progress.py` - export progress dialog
- `settings_store.py` - persistent settings
- `online_installer_qt.py` - installer UI logic
- `packaging/` - build and release scripts
- `hybrid_nextgen/` - experimental QML/C++ direction

## Notes

- Full offline installers are larger due to multimedia dependencies.
- For compact delivery, use web bootstrap installers.
- Some x86 limitations depend on third-party package support.
