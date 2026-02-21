# Packaging / Installers

## Локальная сборка Windows (x64/x86)

```powershell
./packaging/build_windows.ps1 -Arch x64
./packaging/build_windows.ps1 -Arch x86 -PythonExe "C:\Users\<you>\AppData\Local\Programs\Python\Python311-32\python.exe"
```

Примечание: для текущей ветки с `PySide6` x86-сборка обычно недоступна (нет стабильных win32 wheel у `PySide6`), поэтому основной целевой билд — `x64`.

Артефакты:
- `release_bundle/installers/windows/<arch>/ASCIIStudio_Setup_windows_<arch>.exe` — оффлайн setup wizard
- `release_bundle/installers/windows/<arch>/ASCIIStudio_WebBootstrap_windows_<arch>.exe` — компактный web bootstrap installer
- `release_bundle/installers/windows/<arch>/ASCIIStudio_windows_<arch>_portable.zip` — portable-сборка

## Локальная сборка Linux/macOS

```bash
./packaging/build_linux.sh x64
./packaging/build_macos.sh x64
./packaging/build_macos.sh arm64
```

Артефакты:
- `release_bundle/installers/linux/x64/ASCIIStudio_linux_x64_portable.tar.gz`
- `release_bundle/installers/macos/<arch>/ASCIIStudio_macos_<arch>_portable.zip`

## Сборка полного release-bundle

```powershell
python packaging/assemble_release_bundle.py
```

Создаётся папка:
- `release_bundle/bundle_<timestamp>/`

Внутри:
- `installers/`
- `backup/`
- `source_essentials/`
- `manifests/SHA256SUMS.txt`

## GitHub Actions matrix

Workflow: `.github/workflows/build-installers-matrix.yml`

Собирает:
- Windows x64/x86
- Linux x64
- macOS x64/arm64
