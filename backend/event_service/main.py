import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, func
from typing import List, Any, Optional
import uuid
import httpx
from datetime import datetime, timezone, timedelta
import os
import tempfile

from shared.database import get_db, engine
from shared.models.base import Base
from shared.models.event import Event, EventCategory, EventSeverity
from shared.models.alert import Alert, AlertStatus
from shared.models.face import Face, FaceTag
from shared.schemas.event import EventCreate, EventResponse
from shared.schemas.alert import AlertCreate, AlertResponse, AlertUpdate
from shared.schemas.face import FaceResponse, FaceCreate
from shared.models.camera import Camera

CLIPS_DIR = os.path.join(tempfile.gettempdir(), "ai_nvr_clips")
os.makedirs(CLIPS_DIR, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(title="AI NVR Event & Alert Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/clips", StaticFiles(directory=CLIPS_DIR), name="clips")

TELEGRAM_SERVICE_URL = os.environ.get("TELEGRAM_SERVICE_URL", "http://telegram_service:8005")

async def forward_alert_to_telegram(alert: AlertCreate, camera_name: str = "Unknown"):
    astana_tz = timezone(timedelta(hours=5))
    astana_time = datetime.now(timezone.utc).astimezone(astana_tz)
    formatted_time = astana_time.strftime("%d.%m.%Y %H:%M:%S (Astana)")

    payload = {
        "camera_name": camera_name,
        "event_type": alert.event_type,
        "timestamp": formatted_time,
        "clip_path": alert.clip_url if alert.clip_url else None,
        "metadata": alert.metadata_json if alert.metadata_json else {}
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(f"{TELEGRAM_SERVICE_URL}/alerts/trigger", json=payload)
    except Exception as e:
        print(f"[EventService] ⚠ Failed to send Telegram alert: {e}")

# ================= ALERTS =================

@app.post("/alerts", response_model=AlertResponse)
async def create_alert(
    alert_in: AlertCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    alert = Alert(**alert_in.model_dump())
    db.add(alert)
    await db.commit()
    await db.refresh(alert)

    # Automatically log a System Event for this alert
    sys_event = Event(
        category=EventCategory.ALERT,
        severity=EventSeverity.WARNING,
        description=f"AI Detection: {alert_in.object_type} via {alert_in.event_type}",
        camera_id=alert_in.camera_id
    )
    db.add(sys_event)
    await db.commit()

    if alert_in.telegram_sent:
        camera_name = "Camera"
        try:
            result = await db.execute(select(Camera).filter(Camera.id == alert.camera_id))
            camera = result.scalars().first()
            if camera: camera_name = camera.name
        except Exception:
            pass
        background_tasks.add_task(forward_alert_to_telegram, alert_in, camera_name)

    return alert

@app.get("/alerts", response_model=List[AlertResponse])
async def get_alerts(
    skip: int = 0, limit: int = 100,
    camera_id: Optional[uuid.UUID] = None,
    status: Optional[AlertStatus] = None,
    object_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(Alert).order_by(Alert.created_at.desc())
    if camera_id: query = query.filter(Alert.camera_id == camera_id)
    if status: query = query.filter(Alert.status == status)
    if object_type: query = query.filter(Alert.object_type == object_type)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()

@app.put("/alerts/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(alert_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Alert).filter(Alert.id == alert_id))
    alert = result.scalars().first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.status = AlertStatus.ACKNOWLEDGED
    await db.commit()
    await db.refresh(alert)
    
    # Log acknowledgment
    sys_event = Event(
        category=EventCategory.SYSTEM,
        severity=EventSeverity.INFO,
        description=f"Alert {alert_id} acknowledged",
        camera_id=alert.camera_id
    )
    db.add(sys_event)
    await db.commit()
    return alert

# ================= EVENTS =================

@app.post("/events", response_model=EventResponse)
async def create_event(event_in: EventCreate, db: AsyncSession = Depends(get_db)):
    event = Event(**event_in.model_dump())
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event

@app.get("/events", response_model=List[EventResponse])
async def get_events(
    skip: int = 0, limit: int = 100,
    category: Optional[EventCategory] = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(Event).order_by(Event.created_at.desc())
    if category: query = query.filter(Event.category == category)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()

# ================= FACES =================

@app.get("/faces", response_model=List[FaceResponse])
async def get_faces(
    skip: int = 0, limit: int = 100,
    is_known: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(Face).order_by(Face.last_seen.desc())
    if is_known is not None: query = query.filter(Face.is_known == is_known)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()

@app.post("/faces", response_model=FaceResponse)
async def create_face(face_in: FaceCreate, db: AsyncSession = Depends(get_db)):
    face = Face(**face_in.model_dump())
    db.add(face)
    await db.commit()
    await db.refresh(face)
    return face
