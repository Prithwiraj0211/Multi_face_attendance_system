import sys
import os
import time
import socket
from pathlib import Path

# Add current workspace to Python path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

# Ensure UTF-8 console output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

def get_local_ip():
    """Retrieve the machine's local Wi-Fi / LAN IP address for multi-device access."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def main():
    print("=" * 70)
    print("  VISIONPASS - MULTI-FACE REAL-TIME AI ATTENDANCE SYSTEM")
    print("=" * 70)

    # 1. Verify Weights
    weights_dir = ROOT_DIR / "backend" / "weights"
    yunet_path = weights_dir / "face_detection_yunet_2023mar.onnx"
    sface_path = weights_dir / "face_recognition_sface_2021dec.onnx"

    if not yunet_path.exists() or not sface_path.exists():
        print("[*] Downloading neural network weights...")
        import urllib.request
        weights_dir.mkdir(parents=True, exist_ok=True)
        models = {
            yunet_path: "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
            sface_path: "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
        }
        for path, url in models.items():
            if not path.exists() or path.stat().st_size < 10000:
                print(f"[*] Downloading {path.name}...")
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req) as resp, open(path, "wb") as f:
                    f.write(resp.read())
        print("[+] Models verified and ready.")

    local_ip = get_local_ip()

    print(f"\n[+] SERVER ACCESS URLS (Available on ANY connected Wi-Fi / LAN device):")
    print(f"   > Local Kiosk:      http://127.0.0.1:8000/kiosk")
    print(f"   > Wi-Fi / LAN Kiosk:http://{local_ip}:8000/kiosk")
    print(f"   > Admin Portal:     http://127.0.0.1:8000/admin")
    print(f"   > Initial Login:    Username: admin  |  Password: admin123")
    print(f"   > Interactive API:  http://127.0.0.1:8000/docs")
    print("-" * 70)
    print("[*] Launching FastAPI server...\n")

    import uvicorn
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()
