@echo off
setlocal

python -c "from pathlib import Path; from PIL import Image; src=Path('QWE1R.png') if Path('QWE1R.png').exists() else (Path('QWER.png') if Path('QWER.png').exists() else Path('iconASCII.png')); out=Path('QWE1R.ico'); im=Image.open(src).convert('RGBA'); w,h=im.size; side=max(w,h); canvas=Image.new('RGBA',(side,side),(0,0,0,0)); canvas.paste(im,((side-w)//2,(side-h)//2),im); canvas.save(out, format='ICO', sizes=[(16,16),(24,24),(32,32),(40,40),(48,48),(64,64),(96,96),(128,128),(256,256)])"

pyinstaller --noconfirm --clean ASCIIStudio.spec
if errorlevel 1 exit /b 1

python -c "from pathlib import Path; import zipfile; base=Path('dist')/'ASCIIStudio'; out=Path('release')/'ASCIIStudio_package.zip'; out.parent.mkdir(parents=True,exist_ok=True); out.exists() and out.unlink(); z=zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6); [z.write(p, p.relative_to(base)) for p in base.rglob('*') if p.is_file()]; z.close(); print('Packed:', out)"

if exist dist\ASCIIStudio_OnlineInstaller.exe del /q dist\ASCIIStudio_OnlineInstaller.exe
pyinstaller --noconfirm --clean ASCIIStudio_OnlineInstaller.spec
if errorlevel 1 exit /b 1

if exist dist\ASCIIStudio_WebBootstrap.exe del /q dist\ASCIIStudio_WebBootstrap.exe
pyinstaller --noconfirm --clean ASCIIStudio_WebBootstrap.spec
if errorlevel 1 exit /b 1

python packaging\assemble_release_bundle.py
if errorlevel 1 exit /b 1

endlocal
