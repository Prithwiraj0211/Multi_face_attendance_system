import os
import sys
import re
import atexit
import shutil
import urllib.request
import subprocess
import threading
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
TOOLS_DIR = ROOT_DIR / "tools"

CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"

_tunnel_process = None

def get_cloudflared_path() -> Path:
    """Find system cloudflared or auto-download standalone binary."""
    which_path = shutil.which("cloudflared")
    if which_path:
        return Path(which_path)

    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    exe_path = TOOLS_DIR / "cloudflared.exe"

    if not exe_path.exists() or exe_path.stat().st_size < 1_000_000:
        print("[*] Downloading Cloudflare Tunnel binary (one-time setup for worldwide public link)...")
        req = urllib.request.Request(CLOUDFLARED_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp, open(exe_path, "wb") as f:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    percent = (downloaded / total) * 100
                    print(f"\r[*] Downloading Cloudflare Tunnel: {percent:.1f}% ({downloaded // (1024*1024)} MB)", end="")
            print("\n[+] Cloudflare Tunnel ready.")

    return exe_path

def start_public_tunnel(port: int = 8000) -> str:
    """Launch Cloudflare Quick Tunnel and return the public HTTPS URL."""
    global _tunnel_process
    exe_path = get_cloudflared_path()

    cmd = [str(exe_path), "tunnel", "--url", f"http://127.0.0.1:{port}"]

    # Use creationflags on Windows to avoid interrupting console signals
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

    _tunnel_process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        creationflags=creationflags
    )

    atexit.register(stop_public_tunnel)

    # Read stderr to extract the trycloudflare URL
    public_url = None
    url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

    for _ in range(60): # wait up to 30 seconds
        line = _tunnel_process.stderr.readline()
        if not line:
            continue
        match = url_pattern.search(line)
        if match:
            public_url = match.group(0)
            break

    return public_url

def stop_public_tunnel():
    """Cleanly terminate the tunnel process."""
    global _tunnel_process
    if _tunnel_process and _tunnel_process.poll() is None:
        try:
            _tunnel_process.terminate()
            _tunnel_process.wait(timeout=2)
        except Exception:
            try:
                _tunnel_process.kill()
            except Exception:
                pass
        _tunnel_process = None
