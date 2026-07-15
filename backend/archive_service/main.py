import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from minio import Minio
from minio.error import S3Error
import time
import glob
from typing import List
import tempfile

# MinIO Configuration
MINIO_URL = os.environ.get("MINIO_URL", "localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ROOT_USER", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_ROOT_PASSWORD", "minioadminsecure")
BUCKET_NAME = "nvr-archive"

HLS_OUTPUT_DIR = os.path.join(tempfile.gettempdir(), "hls")

# Initialize MinIO Client
minio_client = Minio(
    MINIO_URL,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)

def ensure_bucket_exists():
    try:
        if not minio_client.bucket_exists(BUCKET_NAME):
            minio_client.make_bucket(BUCKET_NAME)
    except S3Error as err:
        print(f"MinIO error: {err}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_bucket_exists()
    yield

app = FastAPI(title="AI NVR Archive Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ArchiveQuery(BaseModel):
    camera_id: str
    start_time: float # unix timestamp
    end_time: float

@app.post("/archive/sync")
async def sync_hls_to_minio(background_tasks: BackgroundTasks):
    """
    Triggers a background task to scan the HLS output directory
    and upload completed .ts segments to MinIO.
    In a real production environment, this would be a Celery beat task.
    """
    def _sync_task():
        for root, dirs, files in os.walk(HLS_OUTPUT_DIR):
            for file in files:
                if file.endswith(".ts"):
                    file_path = os.path.join(root, file)
                    # The object name will be camera_id/filename
                    rel_path = os.path.relpath(file_path, HLS_OUTPUT_DIR)
                    object_name = rel_path.replace("\\", "/")
                    
                    try:
                        # Check if object already exists to avoid re-uploading
                        minio_client.stat_object(BUCKET_NAME, object_name)
                    except S3Error as e:
                        if e.code == 'NoSuchKey':
                            # Upload file
                            minio_client.fput_object(
                                BUCKET_NAME,
                                object_name,
                                file_path,
                                content_type="video/mp2t"
                            )
    
    background_tasks.add_task(_sync_task)
    return {"message": "Sync started in background"}

@app.post("/archive/search", response_model=List[str])
async def search_archive(query: ArchiveQuery):
    """
    Search for available video segments in MinIO for a given camera and time range.
    """
    prefix = f"{query.camera_id}/"
    segments = []
    try:
        objects = minio_client.list_objects(BUCKET_NAME, prefix=prefix, recursive=True)
        for obj in objects:
            # Here we would parse the timestamp from the filename
            # For simplicity, returning all for the camera
            segments.append(obj.object_name)
        return segments
    except S3Error as e:
        raise HTTPException(status_code=500, detail=str(e))
