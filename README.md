# ultra_ascii_studio
I was bored and decided to create some ASCII art. After visiting many different websites, I couldn’t find a program or site that offered the level of customization I was looking for. So, with the help of Codex, I ended up building one myself… XD

# ASCII Studio

ASCII Studio is a desktop application for converting images, GIFs, and videos into high-quality ASCII visuals.  
It combines a fast conversion pipeline, real-time preview, export tools, and an integrated editor with layers, timeline controls, masks, and node-based workflows.

## Key Features

- Image, GIF, and video input support
- Real-time ASCII preview (toggleable)
- Export to PNG, GIF, MP4, and TXT
- Preset system with save/load support
- Built-in style controls and extended Pro Tools effects
- Embedded editor with:
- Text/media layers
- Mask and crop tools
- Timeline controls
- Audio import and source-audio reuse
- Node workspace (video/audio/data compatible node chains)
- Watermark support with custom watermark text
- Theme system with multiple built-in themes
- Custom theme mode with user colors and custom background (image/video/GIF source options in app flow)
- Welcome/tutorial flow
- Multi-language UI (English, Russian, Chinese)
- Easter eggs and hidden interactions
- Built-in update checker and installer launch flow

## Built-in Update System

ASCII Studio supports remote update feeds.  
The app can check a manifest URL and show update status directly in UI (`Install` / `Later`).

Expected manifest format:

```json
{
  "latest_version": "1.2.1",
  "installer_url": "https://your-domain/releases/ASCIIStudio_Setup_windows_x64.exe",
  "notes": "Bug fixes and performance improvements"
}
Supported keys:

latest_version (required)
installer_url or url (required)
notes (optional)
Tech Stack
Python
PySide6 (Qt)
Pillow
NumPy
OpenCV
imageio / imageio-ffmpeg
psutil
Experimental next-gen runtime files are included:

hybrid_nextgen/ (QML + C++ bridge direction)
Installers and Packaging
Available artifact types:

Offline installer (Windows): ASCIIStudio_Setup.exe
Web bootstrap installer (compact): ASCIIStudio_WebBootstrap.exe
Portable package: ASCIIStudio_package.zip
Build
Quick local build (Windows)
powershell

build_release.bat
This script builds:

Main app
Portable package
Offline setup installer
Web bootstrap installer
Release bundle structure
Platform scripts
Windows: build_windows.ps1
Linux: build_linux.sh
macOS: build_macos.sh
CI
GitHub Actions matrix workflow:

build-installers-matrix.yml
Targets:

Windows x64
Linux x64
macOS x64
macOS arm64
Repository Structure
ascii_studio_qt.py — main desktop app
render_worker.py — rendering worker logic
export_progress.py — export progress UI
settings_store.py — settings persistence
online_installer_qt.py — installer UI logic
packaging/ — build/packaging scripts
hybrid_nextgen/ — experimental QML/C++ direction
Notes
Full offline installers are larger because of multimedia dependencies.
For compact distribution, use web bootstrap builds.
x86 Windows builds may be limited by dependency availability.
Version
Current app line: v1.x (with integrated update-feed support).



