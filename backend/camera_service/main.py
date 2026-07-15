import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete
from typing import List, Any
import uuid

from shared.database import get_db, engine
from shared.models.base import Base
from shared.models.camera import Camera
from shared.schemas.camera import CameraCreate, CameraUpdate, CameraResponse

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(title="AI NVR Camera Service", lifespan=lifespan)

# CORS — allow frontend to call the API directly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ══════════════════════════════════════════════════
#  Public / Internal endpoints (no auth)
#  Used by CV Engine and Frontend for zone config
# ══════════════════════════════════════════════════

@app.get("/cameras/{camera_id}", response_model=CameraResponse)
async def get_camera_public(
    camera_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get a specific camera by ID (internal/public — no auth required)."""
    result = await db.execute(select(Camera).filter(Camera.id == camera_id))
    camera = result.scalars().first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


@app.put("/cameras/{camera_id}", response_model=CameraResponse)
async def update_camera_public(
    camera_id: uuid.UUID,
    camera_update: CameraUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Update a camera (internal/public — no auth for zone configuration)."""
    result = await db.execute(select(Camera).filter(Camera.id == camera_id))
    camera = result.scalars().first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    update_data = camera_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(camera, field, value)

    await db.commit()
    await db.refresh(camera)
    return camera


# ══════════════════════════════════════════════════
#  Protected endpoints (require authentication)
# ══════════════════════════════════════════════════

@app.post("/cameras/", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def create_camera(
    camera_in: CameraCreate, 
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Create a new camera."""
    camera = Camera(**camera_in.model_dump())
    db.add(camera)
    await db.commit()
    await db.refresh(camera)
    return camera

@app.get("/cameras/", response_model=List[CameraResponse])
async def get_cameras(
    skip: int = 0, limit: int = 100, 
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Get all cameras."""
    result = await db.execute(select(Camera).offset(skip).limit(limit))
    return result.scalars().all()
@app.delete("/cameras/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(
    camera_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
) -> None:
    """Delete a camera."""
    result = await db.execute(select(Camera).filter(Camera.id == camera_id))
    camera = result.scalars().first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Cascade delete any associated events first
    from shared.models.event import Event
    await db.execute(delete(Event).filter(Event.camera_id == camera_id))
    
    await db.delete(camera)
    await db.commit()
