# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import copy_metadata


a = Analysis(
    ['ascii_studio_qt.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('icons', 'icons'),
        ('sounds', 'sounds'),
        ('Easter eggs', 'Easter eggs'),
        ('SNERK503.mp3', '.'),
        ('3hg46u.png', '.'),
        ('e6b71d9a95c6c61398bb77477207317a.jpg', '.'),
        ('QWE1R.png', '.'),
        ('QWE1R.ico', '.'),
        ('QWER.png', '.'),
        ('QWER.ico', '.'),
        ('iconASCII.png', '.'),
        ('iconASCII.ico', '.'),
        ('update_manifest.json', '.'),
        ('update_manifest.example.json', '.'),
    ] + copy_metadata('imageio'),
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ASCIIStudio',
    icon='QWE1R.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ASCIIStudio',
)
