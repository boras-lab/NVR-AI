import threading
import uuid
import os
import cv2
import numpy as np
from ultralytics import YOLO
import httpx
import time
import collections
from typing import List, Tuple, Dict, Optional

# Force OpenCV/FFmpeg to use TCP for RTSP (avoids UDP timeout issues)
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

# ══════════════════════════════════════════════════
#  Configuration
# ══════════════════════════════════════════════════

EVENT_SERVICE_URL = os.environ.get("EVENT_SERVICE_URL", "http://event_service:8004")
CAMERA_SERVICE_URL = os.environ.get("CAMERA_SERVICE_URL", "http://camera_service:8002/cameras")

# Shared volume for video clips (mounted in both cv_engine and telegram_service)
CLIP_DIR = "/clips"
os.makedirs(CLIP_DIR, exist_ok=True)

# Active pipelines tracking
active_pipelines: Dict[str, threading.Thread] = {}
stop_events: Dict[str, threading.Event] = {}

# ══════════════════════════════════════════════════
#  YOLO Class Categories
# ══════════════════════════════════════════════════

PERSON_CLASS = 0
VEHICLE_CLASSES = {2, 3, 5, 7}  # car, motorcycle, bus, truck
ANIMAL_CLASSES = {14, 15, 16, 17, 18, 19, 20, 21, 22, 23}  # bird, cat, dog, horse, sheep, cow, elephant, bear, zebra, giraffe
OBJECT_CLASSES = {24, 28} # backpack, suitcase
ALL_TRACKED_CLASSES = [PERSON_CLASS] + list(VEHICLE_CLASSES) + list(ANIMAL_CLASSES) + list(OBJECT_CLASSES)

# ══════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════

        except (KeyError, TypeError) as e:
            print(f"[CV] Skipping malformed line: {line} ({e})")
    return result


def ccw(A: Tuple[int, int], B: Tuple[int, int], C: Tuple[int, int]) -> bool:
    """Returns True if points A, B, C are in counter-clockwise order."""
    return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])

def check_line_crossing(
    prev_center: Tuple[int, int],
    curr_center: Tuple[int, int],
    line: Tuple[int, int, int, int]
) -> bool:
    """
    Check if the line segment from prev_center to curr_center
    intersects with the detection line segment (line[0], line[1]) to (line[2], line[3]).
    """
    A = prev_center
    B = curr_center
    C = (line[0], line[1])
    D = (line[2], line[3])
    
    # Standard line segment intersection check
    return ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D)


def send_alert(camera_id: str, event_type: str, object_type: str, confidence: float, metadata: dict, clip_url: str = "", snapshot_url: str = "", telegram_sent: bool = False):
    """Sends an alert to the Event Service."""
    payload = {
        "camera_id": camera_id,
        "event_type": event_type,
        "object_type": object_type,
        "confidence": confidence,
        "snapshot_url": snapshot_url,
        "clip_url": clip_url,
        "metadata_json": metadata,
        "telegram_sent": telegram_sent
    }
    try:
        httpx.post(f"{EVENT_SERVICE_URL}/alerts", json=payload, timeout=5.0)
        print(f"[CV] Alert sent for camera {camera_id}: {event_type} | {object_type} | clip={clip_url}")
    except Exception as e:
        print(f"[CV] Failed to send alert for camera {camera_id}: {e}")


def save_clip_and_send_alert(frames: list, frame_size: tuple, fps: float, camera_id: str, metadata: dict, object_type: str, confidence: float, telegram_sent: bool):
    """
    Saves buffered frames as an MP4 video clip and a JPG snapshot, then sends the alert.
    Runs in a background thread so it doesn't block the main detection loop.
    """
    try:
        w, h = frame_size
        timestamp = int(time.time() * 1000)
        filename_mp4 = f"{camera_id}_{timestamp}.mp4"
        filename_jpg = f"{camera_id}_{timestamp}.jpg"
        
        filepath_mp4 = os.path.join(CLIP_DIR, filename_mp4)
        filepath_jpg = os.path.join(CLIP_DIR, filename_jpg)

        # Save snapshot (middle frame of the sequence)
        mid_idx = len(frames) // 2
        cv2.imwrite(filepath_jpg, frames[mid_idx])

        # Save video clip
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(filepath_mp4, fourcc, max(fps, 10.0), (w, h))
        for f in frames:
            out.write(f)
        out.release()

        file_size = os.path.getsize(filepath_mp4)
        print(f"[CV] [{camera_id}] Clip & Snapshot saved: {filename_mp4} ({len(frames)} frames, {file_size // 1024}KB)")

        # Create public URLs for the frontend
        # Assuming event_service is exposed on port 8004 to the host
        public_clip_url = f"http://localhost:8004/clips/{filename_mp4}"
        public_snapshot_url = f"http://localhost:8004/clips/{filename_jpg}"

        # Now send the alert with the full URLs
        send_alert(
            camera_id, 
            "Line Crossing", 
            object_type, 
            confidence, 
            metadata, 
            clip_url=public_clip_url, 
            snapshot_url=public_snapshot_url, 
            telegram_sent=telegram_sent
        )

    except Exception as e:
        print(f"[CV] [{camera_id}] Failed to save clip: {e}")
        # Still send the alert without a clip
        send_alert(camera_id, "Line Crossing", object_type, confidence, metadata, clip_url="", snapshot_url="", telegram_sent=telegram_sent)


# ══════════════════════════════════════════════════
#  Pipeline Thread
# ══════════════════════════════════════════════════

def run_pipeline(camera_id: str, rtsp_url: str, stop_event: threading.Event):
    print(f"[CV] [{camera_id}] Starting pipeline using RTSP: {rtsp_url}")
    
    # Load separate YOLO model instance per thread to isolate the tracker states
    model_path = os.path.join(os.path.dirname(__file__), 'preyolov8n.pt')
    local_model = YOLO(model_path)
    
    # Store previous positions for tracking
    track_history: Dict[int, Tuple[int, int]] = {}
    track_age: Dict[int, int] = {}
    line_crossed_timers: Dict[str, float] = {}
    tracked_objects_memory: Dict[str, set] = {}

    # Frame ring buffer for video clip recording (~3 seconds pre-buffer)
    PRE_BUFFER_SIZE = 45
    POST_BUFFER_SIZE = 25
    frame_buffer = collections.deque(maxlen=PRE_BUFFER_SIZE)

    # Pending clip recordings: track_id -> { "pre_frames", "post_frames", "remaining", "metadata", "frame_size" }
    pending_clips: Dict[int, dict] = {}
    
    # Face detection cooldown (don't spam faces every frame)
    last_face_detection_time = 0
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    cap = cv2.VideoCapture(rtsp_url)
    
    frame_w, frame_h = 0, 0
    pixel_lines: List[Tuple[str, Tuple[int, int, int, int]]] = []
    
    current_status = "Offline"
    consecutive_failures = 0
    max_consecutive_failures = 5
    last_line_fetch = 0
    LINE_REFRESH_INTERVAL = 15  # seconds
    estimated_fps = 15.0
    frame_count = 0
    fps_start_time = time.time()
    
    def update_status(status_value: str):
        try:
            httpx.put(f"{CAMERA_SERVICE_URL}/{camera_id}", json={"status": status_value}, timeout=3.0)
            print(f"[CV] [{camera_id}] Updated Camera status to: {status_value}")
        except Exception as e:
            print(f"[CV] [{camera_id}] Failed to update status: {e}")

    def fetch_lines() -> List[dict]:
        try:
            response = httpx.get(f"{CAMERA_SERVICE_URL}/{camera_id}", timeout=5.0)
            if response.status_code == 200:
                return response.json().get("detection_lines", [])
        except Exception as e:
            print(f"[CV] [{camera_id}] Failed to fetch lines: {e}")
        return []

    while not stop_event.is_set():
        if not cap.isOpened():
            consecutive_failures += 1
            print(f"[CV] [{camera_id}] RTSP stream not opened ({consecutive_failures}/{max_consecutive_failures}). Retrying in 5s...")
            if consecutive_failures >= max_consecutive_failures:
                if current_status != "Offline":
                    update_status("Offline")
                    current_status = "Offline"
            # Wait with check for stop_event
            for _ in range(5):
                if stop_event.is_set():
                    break
                time.sleep(1)
            cap = cv2.VideoCapture(rtsp_url)
            continue

        success, frame = cap.read()
        if not success:
            consecutive_failures += 1
            print(f"[CV] [{camera_id}] Frame read failed ({consecutive_failures}/{max_consecutive_failures}), retrying in 2s...")
            if consecutive_failures >= max_consecutive_failures:
                if current_status != "Offline":
                    update_status("Offline")
                    current_status = "Offline"
            # Wait with check for stop_event
            for _ in range(2):
                if stop_event.is_set():
                    break
                time.sleep(1)
            cap = cv2.VideoCapture(rtsp_url)
            continue

        # Successfully read a frame -> set status to Online
        consecutive_failures = 0
        if current_status != "Online":
            update_status("Online")
            current_status = "Online"

        h, w = frame.shape[:2]

        # Estimate FPS for clip saving
        frame_count += 1
        elapsed = time.time() - fps_start_time
        if elapsed > 5.0:
            estimated_fps = frame_count / elapsed
            frame_count = 0
            fps_start_time = time.time()

        # Periodically re-fetch lines
        if time.time() - last_line_fetch > LINE_REFRESH_INTERVAL:
            raw_lines = fetch_lines()
            pixel_lines = denormalize_lines(raw_lines, w, h)
            last_line_fetch = time.time()
            
        current_time = time.time()

        # Run YOLO with ByteTrack on the CLEAN frame
        results = local_model.track(
            frame, 
            persist=True, 
            tracker="bytetrack.yaml", 
            conf=0.10,  # Force internal YOLO threshold very low for far objects
            verbose=False,
            imgsz=1024  # High resolution for far-away objects
        )

        # Face Detection on the CLEAN frame (run every 2 seconds to avoid overload)
        if current_time - last_face_detection_time > 2.0:
            last_face_detection_time = current_time
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(50, 50))
            
            for (fx, fy, fw, fh) in faces:
                # Crop and save the face
                face_crop = frame[fy:fy+fh, fx:fx+fw]
                face_ts = int(time.time() * 1000)
                face_filename = f"face_{camera_id}_{face_ts}.jpg"
                face_filepath = os.path.join(CLIP_DIR, face_filename)
                cv2.imwrite(face_filepath, face_crop)
                
                face_url = f"http://localhost:8004/clips/{face_filename}"
                
                # Send to faces API
                payload = {
                    "camera_id": camera_id,
                    "is_known": False,
                    "tag": "Unknown",
                    "photo_url": face_url
                }
                try:
                    # Run in background to avoid blocking, safely binding payload
                    threading.Thread(
                        target=httpx.post,
                        args=(f"{EVENT_SERVICE_URL}/faces",),
                        kwargs={"json": payload, "timeout": 3.0},
                        daemon=True
                    ).start()
                    print(f"[CV] [{camera_id}] Face detected and sent: {face_url}")
                except Exception as e:
                    print(f"[CV] [{camera_id}] Failed to send face: {e}")
                
                # Only process the largest face in the frame at one time to prevent spam
                break

        # Process YOLO detections
        if results[0].boxes.id is not None:
            boxes = results[0].boxes.xywh.cpu()
            track_ids = results[0].boxes.id.int().cpu().tolist()
            classes = results[0].boxes.cls.int().cpu().tolist()
            confs = results[0].boxes.conf.cpu().tolist()

            for box, track_id, cls, conf in zip(boxes, track_ids, classes, confs):
                x, y, bw, bh = box
                curr_center = (int(x), int(y + bh / 2))

                # Track age to prevent ghost/glitch detections
                track_age[track_id] = track_age.get(track_id, 0) + 1

                class_name = local_model.names[cls]
                is_person = (class_name.lower() in ["person", "human", "pedestrian", "man", "woman"])
                is_animal = (class_name.lower() in ["bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "animal"])
                is_vehicle = (class_name.lower() in ["car", "motorcycle", "bus", "truck", "vehicle", "bicycle"])
                is_object_class = (class_name.lower() in ["backpack", "suitcase", "bag"])

                # ── Strict validation for PERSONS ──
                # Lower thresholds to detect people from afar even with poor quality
                is_valid_person = False
                if is_person:
                    if conf >= 0.10: # Just trust the custom model if it finds anything
                        is_valid_person = True

                # ── Animals: always valid for stats (lower threshold) ──
                is_valid_animal = False
                if is_animal:
                    if conf >= 0.45 and track_age[track_id] >= 5:
                        is_valid_animal = True

                # ── Vehicles: valid with basic threshold ──
                is_valid_vehicle = False
                if is_vehicle:
                    if conf >= 0.50 and track_age[track_id] >= 3:
                        is_valid_vehicle = True
                        
                # ── Objects (Backpack, etc) ──
                is_valid_object = False
                if is_object_class:
                    if conf >= 0.50 and track_age[track_id] >= 3:
                        is_valid_object = True

                is_valid = is_valid_person or is_valid_animal or is_valid_vehicle or is_valid_object

                # Check Line Crossing for each detection line
                if is_valid and track_id in track_history:
                    prev_center = track_history[track_id]

                    for line_id, line_coords in pixel_lines:
                        if line_id not in tracked_objects_memory:
                            tracked_objects_memory[line_id] = set()

                        if check_line_crossing(prev_center, curr_center, line_coords):
                            if track_id not in tracked_objects_memory[line_id]:
                                metadata = {
                                    "track_id": track_id,
                                    "class": class_name,
                                    "confidence": round(conf, 2),
                                    "line_id": line_id,
                                    "direction": "crossed"
                                }

                                if is_valid:
                                    should_send_tg = is_valid_person  # Only notify on TG for persons by default
                                    pending_clips[track_id] = {
                                        "pre_frames": list(frame_buffer),
                                        "post_frames": [],
                                        "remaining": POST_BUFFER_SIZE,
                                        "metadata": metadata,
                                        "object_type": class_name,
                                        "confidence": float(conf),
                                        "telegram_sent": should_send_tg,
                                        "frame_size": (w, h)
                                    }
                                    print(f"[CV] [{camera_id}] 📷 {class_name.upper()} crossed line {line_id} — recording clip...")

                                tracked_objects_memory[line_id].add(track_id)
                                line_crossed_timers[line_id] = time.time()

                if is_valid:
                    track_history[track_id] = curr_center
                    # Draw bounding box for visualization
                    color = (0, 255, 0) if is_person else (255, 165, 0) if is_animal else (255, 0, 0)
                    cv2.rectangle(frame, (int(x-bw/2), int(y-bh/2)), (int(x+bw/2), int(y+bh/2)), color, 2)
                    cv2.putText(frame, f"{class_name} {track_id}", (int(x-bw/2), int(y-bh/2)-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                else:
                    # If invalid, drop from history so a glitch doesn't jump across the line later
                    if track_id in track_history:
                        del track_history[track_id]

        # Draw detection lines on the frame
        for line_id, lc in pixel_lines:
            if line_id in line_crossed_timers and (current_time - line_crossed_timers[line_id]) < 3.0:
                color = (0, 255, 255)  # Yellow in BGR
                thickness = 4
            else:
                color = (0, 165, 255)  # Orange/Gold in BGR
                thickness = 2
            cv2.line(frame, (lc[0], lc[1]), (lc[2], lc[3]), color, thickness)

        # Add fully-drawn frame to ring buffer for clip recording
        frame_buffer.append(frame.copy())

        # Update any pending clip post-buffers
        for tid in list(pending_clips.keys()):
            pending_clips[tid]["post_frames"].append(frame.copy())
            pending_clips[tid]["remaining"] -= 1
            if pending_clips[tid]["remaining"] <= 0:
                # Clip is ready — save it in a background thread
                clip_data = pending_clips.pop(tid)
                all_frames = clip_data["pre_frames"] + clip_data["post_frames"]
                t = threading.Thread(
                    target=save_clip_and_send_alert,
                    args=(all_frames, clip_data["frame_size"], estimated_fps, camera_id, clip_data["metadata"], clip_data["object_type"], clip_data["confidence"], clip_data["telegram_sent"]),
                    daemon=True
                )
                t.start()

    cap.release()
    print(f"[CV] [{camera_id}] Pipeline stopped.")


def monitor_cameras():
    print("[CV] Starting Multi-Camera Monitor Service...")
    while True:
        try:
            response = httpx.get(f"{CAMERA_SERVICE_URL}/", timeout=5.0)
            if response.status_code == 200:
                cameras = response.json()
                active_ids = set()
                
                for cam in cameras:
                    cam_id = str(cam["id"])
                    rtsp_url = cam["rtsp_url"]
                    active_ids.add(cam_id)
                    
                    # Start thread if not already running
                    if cam_id not in active_pipelines or not active_pipelines[cam_id].is_alive():
                        stop_event = threading.Event()
                        thread = threading.Thread(
                            target=run_pipeline, 
                            args=(cam_id, rtsp_url, stop_event),
                            daemon=True
                        )
                        thread.start()
                        active_pipelines[cam_id] = thread
                        stop_events[cam_id] = stop_event
                
                # Stop threads for cameras that were deleted
                for cam_id in list(active_pipelines.keys()):
                    if cam_id not in active_ids:
                        print(f"[CV] Stopping pipeline for deleted camera: {cam_id}")
                        stop_events[cam_id].set()
                        del active_pipelines[cam_id]
                        del stop_events[cam_id]
            else:
                print(f"[CV] Camera Service error: {response.status_code}")
        except Exception as e:
            print(f"[CV] Error in camera monitor: {e}")
            
        time.sleep(10)


if __name__ == "__main__":
    monitor_cameras()
