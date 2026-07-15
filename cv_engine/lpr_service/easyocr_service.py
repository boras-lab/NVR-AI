import cv2
import numpy as np
import os

try:
    import easyocr
    from ultralytics import YOLO
    LPR_AVAILABLE = True
except ImportError:
    LPR_AVAILABLE = False

class LicensePlateRecognizer:
    def __init__(self, use_gpu: bool = True):
        if LPR_AVAILABLE:
            # We assume 'yolov8n_plate.pt' is a finetuned model for license plate detection
            # For this mock, we just use standard YOLO and pretend it finds plates
            self.detector = YOLO('yolov8n.pt') 
            self.reader = easyocr.Reader(['en'], gpu=use_gpu)
            print("LPR Engine initialized (YOLO + EasyOCR).")
        else:
            print("WARNING: easyocr or ultralytics not found. Running in dummy mode.")

    def recognize(self, frame: np.ndarray) -> list:
        """Detects plates and reads the text."""
        results = []
        if not LPR_AVAILABLE: return results

        # 1. Detect Plate using YOLO (using standard YOLOv8n here just for structure)
        # Assuming class id '2' (car) is used as a proxy for the vehicle containing the plate
        detections = self.detector.predict(frame, classes=[2, 3, 5, 7]) # vehicles
        
        for box in detections[0].boxes.xyxy.cpu().numpy():
            x1, y1, x2, y2 = map(int, box)
            
            # Simulated: Extract a sub-region where the plate would typically be
            h = y2 - y1
            plate_y1 = int(y2 - (h * 0.2))
            
            plate_crop = frame[plate_y1:y2, x1:x2]
            
            if plate_crop.size > 0:
                # 2. Read Text using EasyOCR
                ocr_results = self.reader.readtext(plate_crop)
                
                # Heuristic: Find text that looks like a license plate
                for (bbox, text, prob) in ocr_results:
                    # Clean up text (remove spaces, special chars)
                    cleaned_text = ''.join(e for e in text if e.isalnum()).upper()
                    
                    if len(cleaned_text) >= 4 and prob > 0.4:
                        results.append({
                            "vehicle_bbox": [x1, y1, x2, y2],
                            "plate_text": cleaned_text,
                            "confidence": float(prob)
                        })
                        
        return results

if __name__ == "__main__":
    # Test execution
    lpr = LicensePlateRecognizer(use_gpu=False)
