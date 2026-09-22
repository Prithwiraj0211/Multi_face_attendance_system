import asyncio
import cv2
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from backend.app.ml.camera import camera_manager

router = APIRouter()

async def generate_mjpeg_frames(use_annotated: bool = True):
    """Async generator for streaming live MJPEG camera frames without blocking threads."""
    try:
        while True:
            if use_annotated:
                frame = camera_manager.get_annotated_frame()
            else:
                frame = camera_manager.get_latest_frame()

            if frame is None:
                await asyncio.sleep(0.04)
                continue

            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ret:
                await asyncio.sleep(0.04)
                continue

            frame_bytes = buffer.tobytes()
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n'
            )
            await asyncio.sleep(0.033) # ~30 FPS
    except (asyncio.CancelledError, GeneratorExit):
        return

@router.get("/video_feed")
async def video_feed():
    """Live MJPEG video stream with real-time multi-face bounding boxes and cyber HUD."""
    return StreamingResponse(
        generate_mjpeg_frames(use_annotated=True),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@router.get("/raw_feed")
async def raw_feed():
    """Clean raw camera video stream without annotations for face capture dialog."""
    return StreamingResponse(
        generate_mjpeg_frames(use_annotated=False),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )
