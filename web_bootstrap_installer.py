from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path


APP_NAME = "ASCIIStudio"


def _quote_ps(s: str) -> str:
    return s.replace("'", "''")


def _default_install_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("ProgramFiles", r"C:\Program Files")
        return Path(base) / APP_NAME
    return Path.home() / APP_NAME


def _download(url: str, dst: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}-WebBootstrap/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp, dst.open("wb") as f:
        shutil.copyfileobj(resp, f)


def _resolve_package_url(manifest_url: str | None, package_url: str | None) -> str:
    if package_url:
        return package_url.strip()
    if not manifest_url:
        raise RuntimeError("Either --package-url or --manifest-url is required")
    req = urllib.request.Request(manifest_url, headers={"User-Agent": f"{APP_NAME}-WebBootstrap/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    for key in ("package_url", "portable_url", "installer_package_url"):
        val = str(data.get(key, "") or "").strip()
        if val:
            return val
    raise RuntimeError("Manifest does not contain package_url/portable_url/installer_package_url")


def _extract_zip(zip_path: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(out_dir)
    exe_candidates = [
        out_dir / APP_NAME / f"{APP_NAME}.exe",
        out_dir / f"{APP_NAME}.exe",
        out_dir / APP_NAME,
    ]
    for c in exe_candidates:
        if c.exists():
            return c
    return out_dir


def _create_desktop_shortcut(target: Path) -> None:
    if os.name != "nt":
        return
    desktop = Path(os.path.join(os.environ.get("USERPROFILE", ""), "Desktop"))
    if not desktop.exists():
        return
    lnk = desktop / "ASCII Studio.lnk"
    icon = target if target.suffix.lower() == ".exe" else (target / "QWER.ico")
    if not icon.exists():
        icon = target if target.suffix.lower() == ".exe" else (target / "_internal" / "QWER.ico")
    ps = (
        "$w = New-Object -ComObject WScript.Shell;"
        f"$s = $w.CreateShortcut('{_quote_ps(str(lnk))}');"
        f"$s.TargetPath = '{_quote_ps(str(target))}';"
        f"$s.WorkingDirectory = '{_quote_ps(str(target.parent))}';"
        f"$s.IconLocation = '{_quote_ps(str(icon))},0';"
        "$s.Save();"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _harden_installation(out_dir: Path) -> None:
    try:
        if os.name == "nt":
            subprocess.run(
                f'attrib +R "{str(out_dir)}\\*" /S /D',
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=True,
            )
            sid_admin = "*S-1-5-32-544"
            sid_system = "*S-1-5-18"
            sid_users = "*S-1-5-32-545"
            subprocess.run(
                [
                    "icacls", str(out_dir),
                    "/grant:r",
                    f"{sid_admin}:(OI)(CI)F",
                    f"{sid_system}:(OI)(CI)F",
                    f"{sid_users}:(OI)(CI)RX",
                    "/T", "/C", "/Q",
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            for p in out_dir.rglob("*"):
                if p.is_file():
                    try:
                        p.chmod(0o644)
                    except Exception:
                        pass
    except Exception:
        pass


def _is_admin_windows() -> bool:
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _ensure_write_access(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".__write_test__"
    with probe.open("w", encoding="utf-8") as f:
        f.write("ok")
    probe.unlink(missing_ok=True)


def main() -> int:
    p = argparse.ArgumentParser(description="ASCII Studio web bootstrap installer")
    p.add_argument("--manifest-url", default="", help="JSON manifest URL with package_url key")
    p.add_argument("--package-url", default="", help="Direct URL to ASCIIStudio package zip")
    p.add_argument("--out-dir", default=str(_default_install_dir()), help="Install directory")
    p.add_argument("--desktop-shortcut", action="store_true", help="Create desktop shortcut (Windows)")
    p.add_argument("--run-after", action="store_true", help="Run app after install")
    args = p.parse_args()

    out_dir = Path(args.out_dir).expanduser().resolve()
    print(f"[1/4] Resolve package URL...")
    package_url = _resolve_package_url(args.manifest_url or None, args.package_url or None)
    print(f"      URL: {package_url}")

    if os.name == "nt" and str(out_dir).lower().startswith(str(Path(os.environ.get("ProgramFiles", r"C:\Program Files"))).lower()):
        if not _is_admin_windows():
            print("[WARN] Installing into Program Files may require Administrator privileges.")

    print("[2/4] Download package...")
    tmp = Path(tempfile.gettempdir()) / "ASCIIStudio_package_web.zip"
    _download(package_url, tmp)
    print(f"      Downloaded: {tmp} ({tmp.stat().st_size} bytes)")

    print("[3/4] Extract package...")
    _ensure_write_access(out_dir)
    target = _extract_zip(tmp, out_dir)
    print(f"      Installed to: {out_dir}")

    print("[4/4] Protecting installation files...")
    _harden_installation(out_dir)

    if args.desktop_shortcut and os.name == "nt":
        print("[5/5] Creating desktop shortcut...")
        _create_desktop_shortcut(target if target.suffix.lower() == ".exe" else (target / f"{APP_NAME}.exe"))
    else:
        print("[5/5] Finalizing...")

    if args.run_after:
        exe = target if target.suffix.lower() == ".exe" else (out_dir / APP_NAME / f"{APP_NAME}.exe")
        if exe.exists():
            subprocess.Popen([str(exe)], shell=False)

    print("Done.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[ERROR] {exc}")
        raise SystemExit(1)
