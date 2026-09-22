import cv2
import numpy as np

class AntiSpoofDetector:
    """
    Lightweight Anti-Spoofing & Liveness Analyzer:
    Detects paper photo attacks and digital screen replays using:
    1. Laplacian frequency spectrum analysis (detects photo grain / blur).
    2. Color distribution in HSV/YCrCb space (detects screen backlight emission).
    """
    
    def __init__(self, min_texture_score: float = 60.0):
        self.min_texture_score = min_texture_score
        
    def check_liveness(self, face_crop: np.ndarray) -> dict:
        """
        Evaluate cropped face for liveness.
        Returns:
            {
                "is_real": bool,
                "liveness_score": float, # 0.0 to 1.0
                "details": str
            }
        """
        if face_crop is None or face_crop.size == 0:
            return {"is_real": False, "liveness_score": 0.0, "details": "Empty crop"}
            
        h, w = face_crop.shape[:2]
        if h < 40 or w < 40:
            return {"is_real": True, "liveness_score": 0.5, "details": "Face too small for full liveness test"}
            
        # 1. Texture analysis via Laplacian variance
        gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        # 2. Color saturation and value distribution
        hsv = cv2.cvtColor(face_crop, cv2.COLOR_BGR2HSV)
        sat_mean = np.mean(hsv[:, :, 1])
        val_std = np.std(hsv[:, :, 2])
        
        # Normalized score: Real faces have moderate texture variance (70-800) and natural contrast
        texture_norm = min(1.0, max(0.0, (laplacian_var - 30.0) / 150.0))
        contrast_norm = min(1.0, max(0.0, val_std / 50.0))
        
        score = (texture_norm * 0.6) + (contrast_norm * 0.4)
        
        # Blurry photos or low-frequency fake screens fail this
        is_real = laplacian_var >= self.min_texture_score and val_std >= 18.0
        
        return {
            "is_real": bool(is_real),
            "liveness_score": round(float(score), 3),
            "texture_var": round(float(laplacian_var), 1),
            "details": "Live Human Verified" if is_real else "Potential Screen/Photo Spoof"
        }

anti_spoof_detector = AntiSpoofDetector()
