# VisionPass - Multi-Face AI Attendance Recognition System

<p align="left">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python" alt="Python Version" />
  <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg?logo=fastapi" alt="FastAPI" />
  <img src="https://img.shields.io/badge/OpenCV-YuNet%20%7C%20SFace-5C3EE8.svg?logo=opencv" alt="OpenCV" />
  <img src="https://img.shields.io/badge/Database-PostgreSQL%20%7C%20SQLite-336791.svg?logo=postgresql" alt="Database" />
  <img src="https://img.shields.io/badge/WebSockets-Real--Time-success.svg" alt="WebSockets" />
</p>

A production-grade, multi-face biometric attendance recognition system built with **FastAPI**, **OpenCV**, **Deep Learning (YuNet + SFace/ArcFace ONNX)**, **PostgreSQL** (with self-healing SQLite fallback), and a modern glassmorphic web portal featuring both a **Full-Screen Live Attendance Kiosk** and a comprehensive **Admin Management Dashboard**.

Unlike traditional single-face systems, this system is capable of detecting and recognizing **multiple employees in a single camera frame simultaneously** in real-time, executing smart debouncing to prevent duplicate punches, validating liveness to reject photo/screen spoofs, and persisting encrypted vector embeddings.

---

## Key Features

1. **Simultaneous Multi-Face Recognition**: Detects, aligns, and identifies 5–10+ faces in a single frame at 30–60 FPS on standard CPUs without requiring heavy GPU clusters.
2. **OpenCV Backend Hardware Camera**: Directly interfaces with USB webcams, integrated laptop cameras, or network RTSP camera streams.
3. **1-Click Face Enrollment**:
   - **Snap Face from Live Camera**: Admins can enroll an employee in 1-click by grabbing their face directly from the live video feed.
   - **Upload Photo File**: Alternatively, upload an existing headshot photograph.
4. **Debounce & Smart Punch State Machine**:
   - Automatic determination of **Check-In** (first detection of the day) vs **Check-Out** (departure).
   - Configurable cooldown (default 5 minutes) prevents repetitive database logging for people lingering in front of the camera.
5. **Biometric Privacy & Cybersecurity**:
   - Passwords secured with salted `bcrypt`.
   - Admin access guarded by JWT Bearer tokens and HTTP-only session cookies.
   - Raw face images are never exposed; identities are matched against normalized 128-D mathematical vector embeddings.
   - Heuristic anti-spoofing analysis (Laplacian frequency and saturation check) prevents photo printout and mobile screen replay attacks.
6. **Dual Database Architecture (PostgreSQL + Self-Healing Fallback)**:
   - Configured out-of-the-box for **PostgreSQL** via SQLAlchemy.
   - Automatically switches to local **SQLite** (`data/attendance.db`) if PostgreSQL is not yet running on the host machine, guaranteeing zero downtime.
7. **Any Wi-Fi / Multi-Device Access**:
   - Server binds to `0.0.0.0:8000`, enabling tablets, phones, or kiosk displays on any office Wi-Fi, LAN, or hotspot to open the terminal.
8. **Real-Time WebSockets & Audio Feedback**:
   - Web Audio synthesizer and Web Speech API announce employee check-ins: *"Welcome, Alex! Check-in confirmed."*
   - Live ticker drawer and toast notifications pop up without page reloads.
9. **Audit Logs & CSV Export**:
   - Filter attendance by date and punch type.
   - Download complete audit trail as a formatted CSV spreadsheet.

---

## System Architecture

<div align="center">
  <img src="docs/assets/system_architecture.svg" alt="VisionPass System Architecture" width="100%" />
</div>

<br/>

<details>
<summary>📐 <b>Click to view Architecture Flowchart (Mermaid Source)</b></summary>

```mermaid
flowchart TD
    subgraph Kiosk["1. Video Ingestion & Display"]
        CAM["OpenCV VideoCapture(0)"] --> RAW["Raw Video Stream"]
        RAW --> HUD["Live Cyber HUD Overlay"]
        HUD --> MJPEG["MJPEG Video Stream (/api/stream/video_feed)"]
    end

    subgraph AI["2. Multi-Face Deep Learning Pipeline"]
        RAW --> DET["YuNet Multi-Face Detector (ONNX)"]
        DET --> ALIGN["Face Alignment (5 Landmarks)"]
        ALIGN --> LIVENESS["Anti-Spoofing & Liveness Check"]
        LIVENESS --> EMBED["SFace Embedding Extractor (128-D Vectors)"]
        EMBED --> MATCH["Cosine Similarity Matcher (Threshold >= 0.38)"]
    end

    subgraph Logic["3. Debounce & State Machine"]
        MATCH --> DEBOUNCE{"In Cooldown Tracker?<br/>(&lt; 5 min)"}
        DEBOUNCE -- Yes --> SKIP["Skip Duplicate Write"]
        DEBOUNCE -- No --> STATE{"Determine Punch Type<br/>(CHECK_IN / CHECK_OUT)"}
        STATE --> SNAP["Save Photo Proof Snapshot"]
    end

    subgraph Persistence["4. Encrypted Database"]
        STATE --> DB[("Database: PostgreSQL / SQLite<br/>• Employees Table<br/>• Face Embeddings<br/>• Attendance Logs")]
    end

    subgraph Broadcast["5. Real-Time Distribution"]
        STATE --> WS["WebSocket Broadcaster (/api/ws/live-events)"]
        WS --> BROWSER["Kiosk Terminal (Audio Chime & Speech Voice)"]
        WS --> DASH["Admin Dashboard (Live Counters & Ticker)"]
    end
```

</details>

---

## Getting Started

### 1. Prerequisites
- Python 3.10+ (Tested on Python 3.12)
- A connected webcam or USB camera

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. PostgreSQL Setup (Optional but Recommended)

By default, the application is set to connect to PostgreSQL:
```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/attendance_db
```

#### Option A: Local PostgreSQL
1. Create a database named `attendance_db`:
   ```sql
   CREATE DATABASE attendance_db;
   ```
2. Adjust username and password in `.env` if different from `postgres:postgres`.

#### Option B: Free Cloud PostgreSQL (Supabase / Neon / Render)
1. Create a free project on [Supabase](https://supabase.com) or [Neon](https://neon.tech).
2. Copy the connection string into `.env`:
   ```env
   DATABASE_URL="postgresql://user:password@ep-xyz.us-east-1.aws.neon.tech/attendance_db?sslmode=require"
   ```

> **Note:** If PostgreSQL is not active when you start the server, the system **automatically falls back to local SQLite** (`data/attendance.db`). You can start testing immediately without installing PostgreSQL first!

---

### 4. Run the Application

Launch the unified runner:
```bash
python run.py
```

---

## Web Portal Access

Once launched, access the following URLs in your browser:

| Interface | URL | Description |
| :--- | :--- | :--- |
| **Attendance Kiosk** | `http://127.0.0.1:8000/kiosk` | Fullscreen attendance terminal with live camera HUD, speech synthesis, and real-time punch ticker. |
| **Admin Dashboard** | `http://127.0.0.1:8000/admin` | Management portal for adding staff, enrolling faces, viewing statistics, and exporting CSVs. |
| **Admin Login** | `http://127.0.0.1:8000/admin/login` | Default credentials: **`admin`** / **`admin123`** |
| **Interactive API Docs** | `http://127.0.0.1:8000/docs` | Swagger / OpenAPI documentation for all REST & WebSocket endpoints. |

---

## How to Enroll an Employee's Face

1. Log in to the Admin Dashboard at `http://127.0.0.1:8000/admin`.
2. Navigate to the **Employees & Faces** tab.
3. Click **"+ Add New Employee"** and fill in their name, employee code, and department.
4. Click **Save & Proceed to Face Enroll**:
   - **Method 1 (Instant Camera Snap)**: Look directly into your webcam and click **"📸 Snap Face from Live Camera"**. The system captures the face, extracts the 128-D vector embedding, and activates recognition instantly!
   - **Method 2 (Photo Upload)**: Choose a picture file (JPG/PNG) containing the employee's face.

---

## Connecting Over Any Wi-Fi / Hotspot & Public Internet

### Option 1: Over Local Wi-Fi / Hotspot
The server listens on `0.0.0.0:8000`. To open the terminal on any phone, tablet, or laptop on the same Wi-Fi:
1. Run `python run.py`.
2. Open the Wi-Fi IP displayed in the terminal (e.g., `http://192.168.1.15:8000/kiosk`) on your mobile device.

### Option 2: 🌐 Worldwide Public Link (For GitHub & Remote Demo)
To generate an instant, worldwide secure HTTPS link connected directly to your live webcam machine:
```bash
python run.py --public
```
This automatically starts a secure Cloudflare Tunnel and prints public URLs:
```text
🌐 WORLDWIDE PUBLIC ACCESS (SHAREABLE GITHUB / DEMO LINK)
   > Public Kiosk:      https://xxxx.trycloudflare.com/kiosk
   > Public Dashboard:  https://xxxx.trycloudflare.com/admin
```
You can put this link directly in your GitHub repository's **About > Website** section so anyone visiting your GitHub can open the live capturing machine!

---

## Configuration Reference (`.env`)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `DATABASE_URL` | `postgresql://postgres:postgres@`<br>`localhost:5432/attendance_db` | PostgreSQL connection URI |
| `CAMERA_INDEX` | `0` | Camera device ID (0 for webcam, or RTSP URL) |
| `FACE_MATCH_THRESHOLD` | `0.38` | SFace cosine similarity cutoff |
| `FACE_DETECTOR_CONF_THRESHOLD` | `0.60` | YuNet detection confidence cutoff |
| `PUNCH_COOLDOWN_SECONDS` | `300` | Cooldown period before repeat punch (5 min) |
| `ADMIN_USERNAME` | `admin` | Default admin username |
| `ADMIN_PASSWORD` | `admin123` | Default admin password |

