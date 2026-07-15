import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import subprocess
import signal
import psutil
import shutil
from typing import Dict, Any
import tempfile

app = FastAPI(title="AI NVR Stream Service (HLS/WebRTC)")

# CORS — allow frontend to call the API and fetch HLS segments
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HLS_OUTPUT_DIR = os.path.join(tempfile.gettempdir(), "hls")
os.makedirs(HLS_OUTPUT_DIR, exist_ok=True)

class CORSStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

# Mount the HLS directory to serve statically
app.mount("/hls", CORSStaticFiles(directory=HLS_OUTPUT_DIR), name="hls")

class StreamStartRequest(BaseModel):
    camera_id: str
    rtsp_url: str

class StreamStatus(BaseModel):
    camera_id: str
    status: str
    hls_url: str | None = None

# Active ffmpeg processes dict: {camera_id: subprocess.Popen}
active_streams: Dict[str, subprocess.Popen] = {}

def kill_stream(camera_id: str):
    if camera_id in active_streams:
        proc = active_streams[camera_id]
        try:
            parent = psutil.Process(proc.pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
        except psutil.NoSuchProcess:
            pass
        del active_streams[camera_id]
        
        # Cleanup old HLS files
        cam_dir = os.path.join(HLS_OUTPUT_DIR, camera_id)
        if os.path.exists(cam_dir):
            shutil.rmtree(cam_dir, ignore_errors=True)

@app.post("/streams/start", response_model=StreamStatus)
async def start_stream(req: StreamStartRequest):
    """Starts FFmpeg process to convert RTSP to HLS."""
    if req.camera_id in active_streams:
        if active_streams[req.camera_id].poll() is None:
            return StreamStatus(
                camera_id=req.camera_id, 
                status="Running",
                hls_url=f"/hls/{req.camera_id}/index.m3u8"
            )
        else:
            kill_stream(req.camera_id)

    cam_dir = os.path.join(HLS_OUTPUT_DIR, req.camera_id)
    os.makedirs(cam_dir, exist_ok=True)
    m3u8_path = os.path.join(cam_dir, "index.m3u8")

    # FFmpeg command to capture RTSP, copy video codec, output as HLS
    # Very low latency tuning for HLS
    ffmpeg_cmd = [
        "ffmpeg",
        "-rtsp_transport", "tcp",
        "-i", req.rtsp_url,
        "-c:v", "copy",
        "-c:a", "aac",
        "-f", "hls",
        "-hls_time", "2",
        "-hls_list_size", "5",
        "-hls_flags", "delete_segments+omit_endlist",
        m3u8_path
    ]

    try:
        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        active_streams[req.camera_id] = proc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start FFmpeg: {str(e)}")

    return StreamStatus(
        camera_id=req.camera_id, 
        status="Started",
        hls_url=f"/hls/{req.camera_id}/index.m3u8"
    )

@app.post("/streams/stop/{camera_id}", status_code=204)
async def stop_stream(camera_id: str):
    if camera_id not in active_streams:
        raise HTTPException(status_code=404, detail="Stream not found")
    kill_stream(camera_id)
    return

@app.get("/streams", response_model=Dict[str, str])
async def list_streams():
    status_dict = {}
    for cid, proc in list(active_streams.items()):
        if proc.poll() is None:
            status_dict[cid] = "Running"
        else:
            status_dict[cid] = "Stopped"
            kill_stream(cid)
    return status_dict
