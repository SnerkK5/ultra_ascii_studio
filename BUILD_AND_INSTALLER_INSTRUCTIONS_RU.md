# ASCII Studio: сборка, backup и инсталляторы

## Что теперь есть

- Оффлайн installer (Windows): `dist/ASCIIStudio_Setup.exe`
- Компактный web-bootstrap installer: `dist/ASCIIStudio_WebBootstrap.exe`
- Portable пакет: `release/ASCIIStudio_package.zip`
- Скрипт сборки release-bundle: `packaging/assemble_release_bundle.py`
- Matrix CI (Windows x64/x86, Linux x64, macOS x64/arm64): `.github/workflows/build-installers-matrix.yml`

## Важно про лимит 30 МБ

С текущим стеком (`PySide6 + OpenCV + imageio + ffmpeg`) полностью **оффлайн** installer в одном `.exe` не может быть <= 30 МБ без вырезания ключевых функций.

Что сделано:
- оставлен полноценный оффлайн installer (все зависимости внутри);
- добавлен компактный web-bootstrap installer для малого размера.

## Быстрая сборка локально (Windows)

```powershell
build_release.bat
```

Скрипт делает:
1. сборку приложения (`ASCIIStudio.spec`);
2. упаковку portable (`release/ASCIIStudio_package.zip`);
3. сборку оффлайн setup (`ASCIIStudio_OnlineInstaller.spec`);
4. сборку компактного web-bootstrap (`ASCIIStudio_WebBootstrap.spec`);
5. сборку папки `release_bundle/bundle_<timestamp>/`.

## Раздельная сборка по платформам/архитектурам

### Windows

```powershell
./packaging/build_windows.ps1 -Arch x64
./packaging/build_windows.ps1 -Arch x86
```

Если на машине несколько Python, можно указать конкретный интерпретатор:

```powershell
./packaging/build_windows.ps1 -Arch x86 -PythonExe "C:\Users\<you>\AppData\Local\Programs\Python\Python311-32\python.exe"
```

Важно: из-за ограничений `PySide6` для win32 x86-сборка может быть недоступна; в таком случае используйте x64 installer.

Артефакты:
- `release_bundle/installers/windows/<arch>/ASCIIStudio_Setup_windows_<arch>.exe`
- `release_bundle/installers/windows/<arch>/ASCIIStudio_WebBootstrap_windows_<arch>.exe`
- `release_bundle/installers/windows/<arch>/ASCIIStudio_windows_<arch>_portable.zip`

### Linux

```bash
./packaging/build_linux.sh x64
```

Артефакт:
- `release_bundle/installers/linux/x64/ASCIIStudio_linux_x64_portable.tar.gz`

### macOS

```bash
./packaging/build_macos.sh x64
./packaging/build_macos.sh arm64
```

Артефакт:
- `release_bundle/installers/macos/<arch>/ASCIIStudio_macos_<arch>_portable.zip`

## Резервная копия проекта

Рекомендуемый формат:
- `backups/ultra_ascii_studio_backup_<timestamp>.zip`

## Обновления внутри приложения

1. Опубликуйте `update_manifest.json` (шаблон: `update_manifest.example.json`).
2. В `~/.ascii_studio_settings.json` задайте `update_feed_url`.
3. В манифесте `installer_url` должен указывать на актуальный installer.

После этого в приложении появится статус обновления и кнопки `Установить / Позже`.
